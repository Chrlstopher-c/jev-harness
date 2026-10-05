"""Écran virtuel (Xvfb) + capture continue vers frame.jpg, pour un navigateur avec fenêtre réelle."""

import shutil
import subprocess
import time
from pathlib import Path
from subprocess import Popen

from loguru import logger

from .events import LIVE_DIR

SIZE = (1366, 768)
X_SOCKETS = Path("/tmp/.X11-unix")


def _free_display() -> int:
    n = 90
    while (X_SOCKETS / f"X{n}").exists():
        n += 1
    return n


class VirtualScreen:
    def __init__(self) -> None:
        self.display: str | None = None
        self._procs: list[Popen[bytes]] = []

    def start(self, grab: bool = True) -> bool:
        if not shutil.which("Xvfb") or (grab and not shutil.which("ffmpeg")):
            logger.warning("Xvfb/ffmpeg absents: navigateur en headless, sans écran virtuel")
            return False
        n = _free_display()
        w, h = SIZE
        if not self._spawn_xvfb(n, w, h):
            return False
        self.display = f":{n}"
        if grab:
            self._spawn_grabber(w, h)
        logger.info("écran virtuel {} {}x{}{}", self.display, w, h, "" if grab else " (sans capture)")
        return True

    def _spawn_xvfb(self, n: int, w: int, h: int) -> bool:
        cmd = ["Xvfb", f":{n}", "-screen", "0", f"{w}x{h}x24", "-nolisten", "tcp"]
        try:
            self._procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except OSError as err:
            logger.error("Xvfb impossible à lancer: {}", err)
            return False
        for _ in range(50):
            if (X_SOCKETS / f"X{n}").exists():
                return True
            time.sleep(0.1)
        logger.error("Xvfb n'a pas démarré")
        self.stop()
        return False

    def _spawn_grabber(self, w: int, h: int) -> None:
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        opts = f"-loglevel error -f x11grab -framerate 3 -video_size {w}x{h} -i {self.display} -q:v 6"
        cmd = ["ffmpeg", *opts.split(), *"-f image2 -update 1 -atomic_writing 1".split(), str(LIVE_DIR / "frame.jpg")]
        try:
            self._procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except OSError as err:
            logger.error("ffmpeg impossible à lancer, pas de capture: {}", err)

    def stop_grab(self) -> None:
        if len(self._procs) > 1:
            self._end(self._procs.pop())

    def stop(self) -> None:
        for p in reversed(self._procs):
            self._end(p)
        self._procs.clear()
        self.display = None

    @staticmethod
    def _end(p: subprocess.Popen) -> None:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
