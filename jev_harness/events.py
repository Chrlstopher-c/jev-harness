"""Journal JSONL d'un run: étapes imbriquées (spans) + notes, lues en direct par le banc d'essai."""
import json
import os
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, TypeVar

LIVE_DIR = Path(os.environ.get("JEV_LIVE", "run/live"))
RUNS_DIR = Path(os.environ.get("JEV_RUNS", "runs"))
_counter = [0]
_local = threading.local()
T = TypeVar("T")


def _stack() -> list[int]:
    if not hasattr(_local, "stack"):
        _local.stack = []
    return _local.stack


def bind(fn: Callable[..., T]) -> Callable[..., T]:
    """Exécute fn dans un thread en rattachant ses événements à l'étape courante du thread appelant."""
    top = _stack()[-1:]

    def run(*args: object, **kwargs: object) -> T:
        _local.stack = list(top)
        return fn(*args, **kwargs)

    return run


def reset() -> None:
    shutil.rmtree(LIVE_DIR, ignore_errors=True)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    _stack().clear()
    _counter[0] = 0


def _write(record: dict) -> None:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    with (LIVE_DIR / "events.jsonl").open("a") as f:
        f.write(json.dumps({"t": time.time(), **record}, ensure_ascii=False) + "\n")


def emit(kind: str, text: str, **data: object) -> None:
    _write({"phase": "note", "parent": _stack()[-1] if _stack() else None, "kind": kind, "text": text, **data})


@contextmanager
def span(kind: str, label: str, **data: object) -> Iterator[dict]:
    _counter[0] += 1
    sid = _counter[0]
    _write({"phase": "begin", "id": sid, "parent": _stack()[-1] if _stack() else None, "kind": kind,
            "label": label, **data})
    _stack().append(sid)
    result: dict = {}
    try:
        yield result
    except Exception:
        result.setdefault("status", "error")
        raise
    finally:
        _stack().pop()
        _write({"phase": "end", "id": sid, "status": result.pop("status", "ok"), **result})


@contextmanager
def timed(kind: str, text: str) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        emit(kind, text, ms=round((time.perf_counter() - t0) * 1000))


def archive() -> None:
    src = LIVE_DIR / "events.jsonl"
    if not src.exists():
        return
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl")
