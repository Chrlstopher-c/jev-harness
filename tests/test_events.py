import json
from pathlib import Path

import pytest

from jev_harness import events


def test_span_nests_and_records_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "LIVE_DIR", tmp_path)
    events.reset()
    with events.span("request", "racine"):
        events.emit("note", "dedans")
        with pytest.raises(ValueError):
            with events.span("step", "echec"):
                raise ValueError("boom")
    rows = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert any(r.get("text") == "dedans" and r["parent"] is not None for r in rows)
    assert any(r.get("status") == "error" for r in rows)


def test_write_survives_unwritable_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "LIVE_DIR", Path("/proc/nope/denied"))
    events.emit("note", "ne doit pas planter")
