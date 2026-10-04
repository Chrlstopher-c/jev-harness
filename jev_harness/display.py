"""Écran virtuel (Xvfb) + capture continue vers frame.jpg, pour un navigateur avec fenêtre réelle."""
import shutil
import subprocess
import time
from pathlib import Path

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
        self._procs: list[subprocess.Popen] = []

    def start(self, grab: bool = True) -> bool:
        if not shutil.which("Xvfb") or (grab and not shutil.which("ffmpeg")):
            logger.warning("Xvfb/ffmpeg absents: navigateur en headless, sans écran virtuel")
            return False
        n = _free_display()
        w, h = SIZE
        xvfb = subprocess.Popen(["Xvfb", f":{n}", "-screen", "0", f"{w}x{h}x24", "-nolisten", "tcp"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._procs.append(xvfb)
        for _ in range(50):
            if (X_SOCKETS / f"X{n}").exists():
                break
            time.sleep(0.1)
        else:
            logger.error("Xvfb n'a pas démarré")
            self.stop()
            return False
        self.display = f":{n}"
        if not grab:
            logger.info("écran virtuel {} {}x{} (sans capture)", self.display, w, h)
            return True
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        grab_proc = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-f", "x11grab", "-framerate", "3", "-video_size", f"{w}x{h}",
             "-i", self.display, "-q:v", "6", "-f", "image2", "-update", "1", "-atomic_writing", "1",
             str(LIVE_DIR / "frame.jpg")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._procs.append(grab_proc)
        logger.info("écran virtuel {} {}x{}", self.display, w, h)
        return True

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
