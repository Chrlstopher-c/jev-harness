from types import SimpleNamespace

import pytest

from jev_harness import llm


def _resp(status: int, headers: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(status_code=status, headers=headers or {}, text="")


def _slot(label: str = "t#1") -> llm.Slot:
    return llm.Slot(label, "http://x", "key-" + label, "m")


def test_parse_json_strips_fences_and_think() -> None:
    raw = '<think>hmm</think>\n```json\n{"a": 1}\n```'
    assert llm.parse_json(raw) == {"a": 1}


def test_parse_json_rejects_garbage_and_non_objects() -> None:
    with pytest.raises(llm.LlmError):
        llm.parse_json("pas du json")
    with pytest.raises(llm.LlmError):
        llm.parse_json("[1, 2]")


def test_pick_rotates_and_skips_dead_or_cooling(monkeypatch: pytest.MonkeyPatch) -> None:
    a, b, c = _slot("a"), _slot("b"), _slot("c")
    b.dead = True
    monkeypatch.setattr(llm, "_slots", [a, b, c])
    monkeypatch.setattr(llm, "_cursor", [0])
    assert llm._pick() is a
    assert llm._pick() is c
    c.cooldown_until = 1e12
    assert llm._pick() is a


def test_rate_limit_sets_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _slot()
    resp = _resp(429, {"retry-after": "7"})
    with pytest.raises(llm.LlmError):
        llm._raise_for_status(s, resp)
    assert 0 < s.cooldown_until
    assert not s.dead


@pytest.mark.parametrize("status", [401, 402, 403])
def test_refused_key_is_marked_dead(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    marked: list[int] = []
    monkeypatch.setattr(llm, "_mark_dead", lambda slot, ttl: (setattr(slot, "dead", True), marked.append(ttl)))
    s = _slot()
    with pytest.raises(llm.LlmError):
        llm._raise_for_status(s, _resp(status))
    assert s.dead and marked


def test_ok_response_does_not_raise() -> None:
    llm._raise_for_status(_slot(), _resp(200))
