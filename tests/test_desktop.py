import json
import threading
from collections.abc import Iterator
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from jev_harness.desktop_ctl import APPS, DesktopCtl, DesktopError
from jev_harness.desktop_server import EVENTS, Handler, _actions
from jev_harness.desktop_stack import Stack

TREE = {
    "type": "root",
    "nodes": [
        {
            "type": "output",
            "nodes": [
                {
                    "type": "workspace",
                    "name": "1",
                    "nodes": [
                        {
                            "id": 5,
                            "type": "con",
                            "pid": 10,
                            "app_id": "foot",
                            "name": "term",
                            "focused": True,
                            "rect": {"x": 0, "y": 28, "width": 800, "height": 600},
                            "nodes": [],
                            "floating_nodes": [],
                        },
                        {
                            "id": 6,
                            "type": "con",
                            "pid": 0,
                            "name": "conteneur",
                            "rect": {},
                            "nodes": [],
                            "floating_nodes": [],
                        },
                    ],
                    "floating_nodes": [
                        {
                            "id": 7,
                            "type": "floating_con",
                            "pid": 11,
                            "name": "xapp",
                            "window_properties": {"class": "Gimp"},
                            "rect": {"x": 5, "y": 5, "width": 300, "height": 200},
                            "nodes": [],
                            "floating_nodes": [],
                        }
                    ],
                }
            ],
        }
    ],
}


class Recorder(DesktopCtl):
    def __init__(self, tmp: Path) -> None:
        super().__init__(Stack(1, 2, tmp))
        self.calls: list[list[str]] = []

    def _msg(self, *args: str) -> str:
        self.calls.append(list(args))
        return json.dumps(TREE) if args[-1] == "get_tree" else ""

    def _run(self, cmd: list[str], data: bool = False):  # noqa: ANN202
        self.calls.append(cmd)
        return None


def test_windows_flattens_tree_and_keeps_only_apps(tmp_path: Path) -> None:
    wins = Recorder(tmp_path).windows()
    assert [(w.id, w.app, w.workspace, w.focused) for w in wins] == [(5, "foot", "1", True), (7, "Gimp", "1", False)]


def test_press_builds_wtype_command(tmp_path: Path) -> None:
    ctl = Recorder(tmp_path)
    ctl.press("ctrl+shift+t")
    assert ctl.calls[-1] == [
        "wtype",
        "-M",
        "ctrl",
        "-M",
        "shift",
        "-P",
        "t",
        "-s",
        "25",
        "-p",
        "t",
        "-m",
        "shift",
        "-m",
        "ctrl",
    ]
    ctl.press("return")
    assert ctl.calls[-1][-5:] == ["-P", "Return", "-s", "25", "-p"] or "Return" in ctl.calls[-1]


@pytest.mark.parametrize("combo", ["", "rm -rf", "ctrl+", "foo+t", "ctrl+shift+é"])
def test_press_rejects_invalid_combos(tmp_path: Path, combo: str) -> None:
    with pytest.raises(DesktopError):
        Recorder(tmp_path).press(combo)


def test_click_moves_then_presses_and_releases(tmp_path: Path) -> None:
    ctl = Recorder(tmp_path)
    ctl.click(10, 20, "right")
    assert ctl.calls == [
        ["seat", "-", "cursor", "set", "10", "20"],
        ["seat", "-", "cursor", "press", "button3"],
        ["seat", "-", "cursor", "release", "button3"],
    ]
    with pytest.raises(DesktopError):
        ctl.click(1, 1, "double")


def test_launch_resolves_app_aliases(tmp_path: Path) -> None:
    ctl = Recorder(tmp_path)
    ctl.launch("terminal")
    ctl.launch("echo salut")
    assert ctl.calls == [["exec", APPS["terminal"]], ["exec", "echo salut"]]


@pytest.fixture
def server(tmp_path: Path) -> Iterator[str]:
    ctl = Recorder(tmp_path)
    ctl.screenshot = lambda: b"\xff\xd8jpeg"  # type: ignore[method-assign]
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, ctl, _actions(ctl)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _call(method: str, url: str, **kwargs: object) -> httpx.Response:
    try:
        return httpx.request(method, url, timeout=5, **kwargs)
    except httpx.HTTPError as err:
        pytest.fail(f"requête {method} {url} échouée: {err}")


def test_http_state_launch_and_journal(server: str) -> None:
    EVENTS.clear()
    assert len(_call("GET", f"{server}/state").json()["windows"]) == 2
    assert _call("POST", f"{server}/launch", json={"cmd": "terminal"}).json() == {"ok": True}
    assert _call("GET", f"{server}/events").json()["events"][-1]["kind"] == "launch"
    assert _call("GET", f"{server}/shot.jpg").headers["content-type"] == "image/jpeg"


def test_http_rejects_bad_requests(server: str) -> None:
    assert _call("POST", f"{server}/click", json={"x": "a"}).status_code == 400
    assert _call("POST", f"{server}/key", json={"keys": "rm -rf"}).status_code == 502
    assert _call("POST", f"{server}/nope", json={}).status_code == 404
    assert _call("GET", f"{server}/nope").status_code == 404
