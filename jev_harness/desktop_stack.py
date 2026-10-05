"""Pile du bureau virtuel: sway headless + wayvnc + websockify, isolée de la session réelle."""

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from loguru import logger

from .desktop_cleanup import PIDS_FILE, kill_stale, record_pid

DESKTOP_DIR = Path(__file__).parent / "desktop"
OUTPUT = "HEADLESS-1"
SOCKET_WAIT_S = 15
PRIVATE_BIN = Path.home() / ".local" / "share" / "jev-desktop"
FOREIGN_ENV = ("DISPLAY", "WAYLAND_DISPLAY", "SWAYSOCK", "I3SOCK", "HYPRLAND_INSTANCE_SIGNATURE", "NIRI_SOCKET")


class StackError(Exception):
    pass


def sway_binary() -> str:
    """Copie de sway sans capability: le cap_sys_nice du paquet active le temps réel et le noyau tue sway (SIGKILL)
    dès que le rendu logiciel headless dépasse la limite CPU temps réel."""
    src = shutil.which("sway")
    if src is None:
        raise StackError("sway n'est pas installé (pacman -S sway)")
    dst = PRIVATE_BIN / "sway"
    if not dst.exists() or dst.stat().st_mtime < Path(src).stat().st_mtime:
        PRIVATE_BIN.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return str(dst)


@dataclass
class Stack:
    vnc_port: int
    ws_port: int
    run_dir: Path
    procs: list[subprocess.Popen] = field(default_factory=list)
    sway_sock: str = ""
    wayland_display: str = ""
    dbus_address: str = ""

    def env(self) -> dict[str, str]:
        """Environnement des applis du bureau virtuel (jamais celui de la session réelle)."""
        base = {k: v for k, v in os.environ.items() if k not in FOREIGN_ENV}
        return {
            **base,
            "WAYLAND_DISPLAY": self.wayland_display,
            "SWAYSOCK": self.sway_sock,
            "XDG_CURRENT_DESKTOP": "sway",
            "XDG_SESSION_TYPE": "wayland",
        }

    def start(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        kill_stale(self.run_dir)
        try:
            self._start_dbus()
            self._start_sway()
            self._spawn(
                "waybar", ["waybar", "-c", str(DESKTOP_DIR / "waybar.jsonc"), "-s", str(DESKTOP_DIR / "waybar.css")]
            )
            self._spawn(
                "wayvnc",
                [
                    "wayvnc",
                    "-C",
                    str(DESKTOP_DIR / "wayvnc.conf"),
                    "-S",
                    str(self.run_dir / "wayvncctl.sock"),
                    "-o",
                    OUTPUT,
                    "-r",
                    "-f",
                    "20",
                    "127.0.0.1",
                    str(self.vnc_port),
                ],
            )
            self._spawn(
                "websockify",
                [sys.executable, "-m", "websockify", f"127.0.0.1:{self.ws_port}", f"127.0.0.1:{self.vnc_port}"],
            )
        except (OSError, StackError) as err:
            logger.error("bureau virtuel impossible à démarrer: {}", err)
            self.stop()
            raise StackError(str(err)) from err
        logger.info("bureau virtuel prêt ({}, vnc {}, ws {})", self.wayland_display, self.vnc_port, self.ws_port)

    def _popen(self, cmd: list[str], env: dict[str, str] | None = None) -> subprocess.Popen:
        log = (self.run_dir / f"{Path(cmd[0]).name}.log").open("w")
        try:
            return subprocess.Popen(cmd, env=env, stdout=log, stderr=log)
        except OSError as err:
            logger.error("{} impossible à lancer: {}", cmd[0], err)
            raise StackError(f"{cmd[0]} impossible à lancer: {err}") from err
        finally:
            log.close()

    def _start_dbus(self) -> None:
        """Bus de session privé: sans lui, Firefox & co. (instance unique) s'ouvriraient chez l'utilisateur."""
        sock = self.run_dir / "bus"
        sock.unlink(missing_ok=True)
        self.dbus_address = f"unix:path={sock}"
        proc = self._popen(["dbus-daemon", "--session", "--nofork", f"--address={self.dbus_address}"])
        self._track(proc)
        self._wait(sock.exists, "bus D-Bus privé", proc)

    def _start_sway(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in FOREIGN_ENV}
        env.update(
            DBUS_SESSION_BUS_ADDRESS=self.dbus_address,
            WLR_BACKENDS="headless",
            WLR_LIBINPUT_NO_DEVICES="1",
            WLR_RENDERER="pixman",
            XDG_CURRENT_DESKTOP="sway",
        )
        proc = self._popen([sway_binary(), "-c", str(DESKTOP_DIR / "sway.conf")], env)
        self._track(proc)
        sock = Path(os.environ["XDG_RUNTIME_DIR"]) / f"sway-ipc.{os.getuid()}.{proc.pid}.sock"
        self._wait(sock.exists, "socket IPC de sway", proc)
        self.sway_sock = str(sock)
        self.wayland_display = self._discover_display(proc)

    def _discover_display(self, proc: subprocess.Popen) -> str:
        probe = self.run_dir / "wayland_display"
        probe.unlink(missing_ok=True)
        cmd = ["swaymsg", "-s", self.sway_sock, "exec", f"sh -c 'echo $WAYLAND_DISPLAY > {probe}'"]
        try:
            subprocess.run(cmd, capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as err:
            logger.error("swaymsg injoignable: {}", err)
            raise StackError(f"swaymsg injoignable: {err}") from err
        self._wait(lambda: probe.exists() and probe.read_text().strip() != "", "nom du socket Wayland", proc)
        return probe.read_text().strip()

    def _spawn(self, name: str, cmd: list[str]) -> None:
        proc = self._popen(cmd, self.env())
        self._track(proc)
        time.sleep(0.4)
        if proc.poll() is not None:
            raise StackError(f"{name} s'est arrêté au démarrage (code {proc.returncode})")

    @staticmethod
    def _wait(cond: Callable[[], bool], what: str, proc: subprocess.Popen) -> None:
        end = time.time() + SOCKET_WAIT_S
        while time.time() < end:
            if proc.poll() is not None:
                raise StackError(f"processus arrêté avant: {what}")
            try:
                if cond():
                    return
            except OSError as err:
                logger.debug("attente de {}: {}", what, err)
            time.sleep(0.1)
        raise StackError(f"délai dépassé: {what}")

    def _track(self, proc: subprocess.Popen) -> None:
        self.procs.append(proc)
        try:
            record_pid(self.run_dir, proc.pid)
        except OSError:
            logger.warning("le nettoyage des orphelins ne connaîtra pas le PID {}", proc.pid)

    def alive(self) -> bool:
        return bool(self.procs) and all(p.poll() is None for p in self.procs)

    def stop(self) -> None:
        for proc in reversed(self.procs):
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        for proc in reversed(self.procs):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.procs.clear()
        (self.run_dir / PIDS_FILE).unlink(missing_ok=True)
