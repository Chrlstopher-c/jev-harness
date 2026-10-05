import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jev_harness import desktop_mcp


def run(coro: Coroutine[Any, Any, Any]) -> Any:  # noqa: ANN401
    """asyncio.run dans un thread: la fixture Playwright de session garde une boucle active dans le thread principal."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class FakeResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def json(self) -> dict:
        return self._data


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict | None]]:
    log: list[tuple[str, str, dict | None]] = []

    async def fake_call(method: str, path: str, body: dict | None = None) -> FakeResponse:
        log.append((method, path, body))
        win = {"id": 5, "app": "foot", "title": "term", "w": 800, "h": 600, "x": 0, "y": 28, "focused": True}
        return FakeResponse({"ready": True, "alive": True, "windows": [win]})

    monkeypatch.setattr(desktop_mcp, "_call", fake_call)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(desktop_mcp.asyncio, "sleep", lambda _s: real_sleep(0))
    return log


def test_summary_states() -> None:
    assert desktop_mcp._summary({"alive": False}) == "Bureau virtuel arrêté"
    assert desktop_mcp._summary({"alive": True, "ready": False}) == "Bureau virtuel en démarrage"
    text = desktop_mcp._summary(
        {
            "ready": True,
            "windows": [{"id": 1, "app": "", "title": "t", "w": 2, "h": 3, "x": 4, "y": 5, "focused": False}],
        }
    )
    assert "#1 ?" in text and "2x3@4,5" in text


def test_do_chains_steps_in_one_call(calls: list[tuple[str, str, dict | None]]) -> None:
    steps = [{"launch": "terminal"}, {"click": [10, 20, "right"]}, {"type": "salut"}, {"key": "ctrl+l"}, {"focus": 5}]
    out = run(desktop_mcp.desktop_do(steps))
    assert out.startswith("5 étape(s) faites.")
    assert [(c[1], c[2]) for c in calls[:5]] == [
        ("launch", {"cmd": "terminal"}),
        ("click", {"x": 10, "y": 20, "button": "right"}),
        ("type", {"text": "salut"}),
        ("key", {"keys": "ctrl+l"}),
        ("focus", {"id": 5}),
    ]


@pytest.mark.parametrize("steps", [[], [{"a": 1, "b": 2}], [{"explode": 1}], [{"click": [1]}], [{"focus": "x"}]])
def test_do_rejects_invalid_steps(calls: list[tuple[str, str, dict | None]], steps: list[dict]) -> None:
    with pytest.raises(ToolError):
        run(desktop_mcp.desktop_do(steps))


def test_do_limits_step_count(calls: list[tuple[str, str, dict | None]]) -> None:
    with pytest.raises(ToolError):
        run(desktop_mcp.desktop_do([{"wait": 0}] * (desktop_mcp.MAX_STEPS + 1)))


def test_base_requires_lab_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAB_URL", raising=False)
    with pytest.raises(ToolError):
        desktop_mcp._base()
