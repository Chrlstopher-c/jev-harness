"""Nettoyage des orphelins du bureau virtuel (serveur tué sans arrêt propre): fichier de PID + vérification."""

import os
import signal
import time
from pathlib import Path

from loguru import logger

PIDS_FILE = "pids"
OURS = ("sway", "wayvnc", "waybar", "dbus-daemon", "websockify")
GRACE_S = 3.0


def record_pid(run_dir: Path, pid: int) -> None:
    try:
        with (run_dir / PIDS_FILE).open("a") as f:
            f.write(f"{pid}\n")
    except OSError as err:
        logger.warning("PID {} non enregistré: {}", pid, err)
        raise


def _is_ours(pid: int) -> bool:
    """Le PID peut avoir été recyclé: on ne tue que si sa ligne de commande est bien un composant du bureau virtuel."""
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
    except OSError:
        return False
    return any(name in cmdline for name in OURS)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def kill_stale(run_dir: Path) -> int:
    """Termine les processus d'un précédent lancement; retourne le nombre de processus visés."""
    path = run_dir / PIDS_FILE
    try:
        pids = [int(x) for x in path.read_text().split()]
    except (OSError, ValueError):
        return 0
    targets = [p for p in pids if _alive(p) and _is_ours(p)]
    for pid in targets:
        _signal(pid, signal.SIGTERM)
    deadline = time.time() + GRACE_S
    while time.time() < deadline and any(_alive(p) for p in targets):
        time.sleep(0.1)
    for pid in targets:
        if _alive(pid):
            _signal(pid, signal.SIGKILL)
    path.unlink(missing_ok=True)
    if targets:
        logger.warning("{} processus orphelin(s) du bureau virtuel nettoyé(s)", len(targets))
    return len(targets)


def _signal(pid: int, sig: signal.Signals) -> None:
    try:
        os.kill(pid, sig)
    except OSError as err:
        logger.debug("signal {} vers {}: {}", sig.name, pid, err)
