"""Capture des images réelles du bureau virtuel pour le banc de vision: n terminaux ouverts -> shots/<n>_<k>.jpg."""

import os
import sys
import time

import httpx
from loguru import logger

from .vision_tasks import SHOTS_DIR

REPEATS = 4
TERMINAL = 'foot -T neutre -e env PS1="$ " sh -i'  # prompt neutre: aucun nom d'hôte ni chemin dans les captures
SETTLE_S = 1.6


def _call(method: str, path: str, body: dict | None = None) -> httpx.Response:
    base = os.environ["LAB_URL"].rstrip("/") + "/api/desktop"
    try:
        r = httpx.request(method, f"{base}/{path}", json=body, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as err:
        logger.error("labo/bureau: {} {} échoué: {}", method, path, err)
        raise
    return r


def _close_all() -> None:
    for win in _call("GET", "state").json()["windows"]:
        _call("POST", "close", {"id": win["id"]})
    time.sleep(0.8)


def main() -> int:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    if not _call("GET", "state").json().get("ready"):
        logger.error("le bureau virtuel n'est pas démarré")
        return 1
    for n in range(1, 5):
        for k in range(REPEATS):
            _close_all()
            for _ in range(n):
                _call("POST", "launch", {"cmd": TERMINAL})
                time.sleep(0.5)
            time.sleep(SETTLE_S)
            seen = len(_call("GET", "state").json()["windows"])
            if seen != n:
                logger.warning("{} fenêtres attendues, {} vues: capture ignorée", n, seen)
                continue
            (SHOTS_DIR / f"{n}_{k}.jpg").write_bytes(_call("GET", "shot.jpg?scale=0.5").content)
    _close_all()
    print(f"{len(list(SHOTS_DIR.glob('*.jpg')))} captures dans {SHOTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
