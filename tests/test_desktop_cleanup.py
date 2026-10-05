import subprocess
import time
from pathlib import Path

import pytest

from jev_harness.desktop_cleanup import PIDS_FILE, kill_stale, record_pid


def _spawn(name: str) -> subprocess.Popen:
    try:
        return subprocess.Popen(["bash", "-c", f"exec -a {name} sleep 60"])
    except OSError as err:
        pytest.fail(f"processus de test impossible à lancer: {err}")


def test_kills_only_our_components_and_clears_file(tmp_path: Path) -> None:
    ours, other = _spawn("wayvnc-test"), subprocess.Popen(["sleep", "60"])
    try:
        record_pid(tmp_path, ours.pid)
        record_pid(tmp_path, other.pid)
        time.sleep(0.2)
        assert kill_stale(tmp_path) == 1
        ours.wait(timeout=5)
        assert other.poll() is None
        assert not (tmp_path / PIDS_FILE).exists()
    finally:
        other.kill()
        ours.kill()


def test_missing_or_corrupt_pid_file_is_ignored(tmp_path: Path) -> None:
    assert kill_stale(tmp_path) == 0
    (tmp_path / PIDS_FILE).write_text("pas un pid")
    assert kill_stale(tmp_path) == 0
