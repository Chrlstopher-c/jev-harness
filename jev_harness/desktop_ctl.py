"""Pilotage du bureau virtuel: fenêtres, lancement d'applis, souris, clavier, capture (sway IPC, wtype, grim)."""

import json
import re
import subprocess
from dataclasses import asdict, dataclass

from loguru import logger

from .desktop_stack import PRIVATE_BIN, Stack

TIMEOUT_S = 8
KEY_HOLD_MS = 25
MODIFIERS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift", "super": "logo", "logo": "logo"}
BUTTONS = {"left": "button1", "middle": "button2", "right": "button3"}
APPS = {
    "terminal": "foot",
    "launcher": "fuzzel",
    "firefox": f"firefox --no-remote --profile {PRIVATE_BIN / 'profiles' / 'firefox'}",
    "chrome": f"google-chrome-stable --user-data-dir={PRIVATE_BIN / 'profiles' / 'chrome'} --ozone-platform=wayland",
}
KEY = re.compile(r"^[A-Za-z0-9_]+$")


class DesktopError(Exception):
    pass


@dataclass
class Window:
    id: int
    app: str
    title: str
    x: int
    y: int
    w: int
    h: int
    focused: bool
    workspace: str


class DesktopCtl:
    def __init__(self, stack: Stack) -> None:
        self.stack = stack

    def _run(self, cmd: list[str], data: bool = False) -> subprocess.CompletedProcess:
        try:
            r = subprocess.run(cmd, env=self.stack.env(), capture_output=True, timeout=TIMEOUT_S, check=False)
        except (OSError, subprocess.TimeoutExpired) as err:
            logger.error("commande {} échouée: {}", cmd[0], err)
            raise DesktopError(f"{cmd[0]}: {err}") from err
        if r.returncode != 0:
            msg = r.stderr.decode(errors="replace").strip()[:200]
            logger.warning("{} code {}: {}", cmd[0], r.returncode, msg)
            raise DesktopError(f"{cmd[0]}: {msg or r.returncode}")
        return r

    def _msg(self, *args: str) -> str:
        return self._run(["swaymsg", "-s", self.stack.sway_sock, *args]).stdout.decode()

    def windows(self) -> list[Window]:
        try:
            tree = json.loads(self._msg("-t", "get_tree"))
        except ValueError as err:
            raise DesktopError(f"arbre sway illisible: {err}") from err
        out: list[Window] = []
        self._collect(tree, "", out)
        return out

    def _collect(self, node: dict, workspace: str, out: list[Window]) -> None:
        if node.get("type") == "workspace":
            workspace = node.get("name", "")
        children = node.get("nodes", []) + node.get("floating_nodes", [])
        if not children and node.get("pid") and node.get("type") in ("con", "floating_con"):
            r = node["rect"]
            app = node.get("app_id") or (node.get("window_properties") or {}).get("class") or ""
            out.append(
                Window(
                    node["id"],
                    app,
                    node.get("name") or "",
                    r["x"],
                    r["y"],
                    r["width"],
                    r["height"],
                    bool(node.get("focused")),
                    workspace,
                )
            )
        for child in children:
            self._collect(child, workspace, out)

    def launch(self, command: str) -> None:
        self._msg("exec", APPS.get(command, command))

    def click(self, x: int, y: int, button: str = "left") -> None:
        key = BUTTONS.get(button)
        if key is None:
            raise DesktopError(f"bouton inconnu: {button}")
        self.move(x, y)
        self._msg("seat", "-", "cursor", "press", key)
        self._msg("seat", "-", "cursor", "release", key)

    def move(self, x: int, y: int) -> None:
        self._msg("seat", "-", "cursor", "set", str(int(x)), str(int(y)))

    def type_text(self, text: str) -> None:
        self._run(["wtype", "-s", str(KEY_HOLD_MS * 4), "--", text])

    def press(self, combo: str) -> None:
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        mods = [MODIFIERS[p] for p in parts[:-1] if p in MODIFIERS]
        key = parts[-1] if parts else ""
        if not KEY.match(key) or key in MODIFIERS or len(mods) != len(parts) - 1:
            raise DesktopError(f"combinaison invalide: {combo}")
        cmd = ["wtype"]
        for m in mods:
            cmd += ["-M", m]
        name = key.capitalize() if len(key) > 1 else key
        cmd += ["-P", name, "-s", str(KEY_HOLD_MS), "-p", name]
        for m in reversed(mods):
            cmd += ["-m", m]
        self._run(cmd)

    def close_window(self, window_id: int) -> None:
        self._msg(f"[con_id={int(window_id)}]", "kill")

    def focus_window(self, window_id: int) -> None:
        self._msg(f"[con_id={int(window_id)}]", "focus")

    def screenshot(self) -> bytes:
        return self._run(["grim", "-t", "jpeg", "-q", "70", "-"]).stdout

    def state(self) -> dict:
        wins = [asdict(w) for w in self.windows()]
        return {"running": self.stack.alive(), "size": [1600, 900], "windows": wins}
