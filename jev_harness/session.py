"""Session interactive: Chromium persistant, flux d'images CDP, entrées de l'utilisateur relayées, commandes."""

import base64
import os
import queue
import signal
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from loguru import logger
from playwright.sync_api import Error as PlaywrightError

from .browser import Browser
from .env import load_env
from .hub import Hub

TICK_MS = 8
STATE_EVERY_S = 1.5
ASK_TIMEOUT_S = 180
CAST = {"format": "jpeg", "quality": 60, "everyNthFrame": 1}
BUTTONS = {0: "left", 1: "middle", 2: "right"}
SEARCH_URL = "https://www.bing.com/search?q="


def normalize_url(text: str) -> str:
    text = text.strip()
    if text.startswith(("http://", "https://", "about:", "data:")):
        return text
    if "." in text and " " not in text:
        return f"https://{text}"
    from urllib.parse import quote_plus

    return SEARCH_URL + quote_plus(text)


class Session:
    def __init__(self) -> None:
        self.hub = Hub()
        self.cmds: queue.Queue[dict] = queue.Queue()
        self.busy = False
        self.stop_requested = False
        self.brain = "cloud"
        self.last_brief: dict | None = None
        self.handoff = False
        self.confirm_enabled = True
        self._replies: dict[str, bool] = {}
        self._answer: str | None = None
        self._awaiting = False
        self.br: Browser | None = None
        self._cdp = None
        self._quit = False
        self._last_state = ""
        self._last_push = 0.0

    def shutdown(self) -> None:
        self._quit = True

    def submit(self, msg: dict) -> None:
        t = msg.get("t")
        if t == "stop":
            self.stop_requested = True
        if t == "confirm_reply":
            self._replies[str(msg.get("id"))] = bool(msg.get("ok"))
            return
        if t == "say" and self._awaiting:
            self._answer, self._awaiting = str(msg.get("text", "")), False
            self.say("user", self._answer)
            return
        self.cmds.put(msg)

    def pump(self, ms: int = 8) -> None:
        self.br.page.wait_for_timeout(ms)
        self._push_state()

    def wait_until(self, cond: Callable[[], bool], timeout_s: float) -> bool:
        end = time.time() + timeout_s
        while time.time() < end and not self.stop_requested:
            if cond():
                return True
            self.pump(50)
        return False

    def confirm(self, text: str) -> bool:
        if not self.confirm_enabled:
            return True
        cid = uuid.uuid4().hex[:8]
        self.hub.broadcast({"t": "confirm", "id": cid, "text": text})
        self.wait_until(lambda: cid in self._replies, ASK_TIMEOUT_S)
        return self._replies.pop(cid, False)

    def ask(self, question: str, timeout_s: float, handoff: bool = False) -> str | None:
        if question:
            self.say("assistant", question)
        self._answer, self._awaiting, self.handoff = None, True, handoff
        try:
            self.wait_until(lambda: self._answer is not None, timeout_s)
        finally:
            self._awaiting, self.handoff = False, False
        return self._answer

    def hello(self, outbox: queue.Queue) -> None:
        outbox.put({"t": "state", **self.state()})

    def state(self) -> dict:
        page = self.br.page if self.br else None
        return {
            "url": page.url if page else "",
            "busy": self.busy,
            "ready": self.br is not None,
            "brain": self.brain,
            "confirm": self.confirm_enabled,
            **self.hub.meta,
        }

    def say(self, role: str, text: str) -> None:
        self.hub.broadcast({"t": "chat", "role": role, "text": text})

    def run(self) -> None:
        try:
            with Browser(grab=False, profile=self._profile_dir()) as br:
                self.br = br
                self._start_cast()
                br.open("about:blank")
                logger.info("session prête")
                while not self._quit:
                    self._tick()
        except Exception:
            logger.exception("la session s'est arrêtée sur une erreur")
            raise

    @staticmethod
    def _profile_dir() -> str:
        path = Path(os.environ.get("SESSION_PROFILE", "data/profile")).resolve()
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
        return str(path)

    def _start_cast(self) -> None:
        page = self.br.page
        self._cdp = page.context.new_cdp_session(page)
        self._cdp.on("Page.screencastFrame", self._on_frame)
        self._cdp.send("Page.startScreencast", CAST)
        page.on("framenavigated", lambda _f: self._restart_cast())

    def _restart_cast(self) -> None:
        try:
            self._cdp.send("Page.stopScreencast")
            self._cdp.send("Page.startScreencast", CAST)
        except Exception as err:
            logger.warning("flux d'images non relancé: {}", err)

    def _on_frame(self, params: dict) -> None:
        meta = params["metadata"]
        self.hub.publish_frame(base64.b64decode(params["data"]), {"w": meta["deviceWidth"], "h": meta["deviceHeight"]})
        try:
            self._cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception as err:
            logger.warning("ack d'image: {}", err)

    def _tick(self) -> None:
        batch: list[dict] = []
        while not self.cmds.empty():
            batch.append(self.cmds.get())
        for cmd in self._coalesce(batch):
            self._dispatch(cmd)
        self.br.page.wait_for_timeout(TICK_MS)
        self._push_state()

    @staticmethod
    def _coalesce(batch: list[dict]) -> list[dict]:
        out: list[dict] = []
        for c in batch:
            if out and c.get("t") == "mouse" and c.get("type") == "move" and out[-1].get("type") == "move":
                out[-1] = c
            else:
                out.append(c)
        return out

    def _push_state(self) -> None:
        now = time.time()
        sig = f"{self.br.page.url}|{self.busy}|{self.hub.meta}"
        if sig != self._last_state or now - self._last_push > STATE_EVERY_S:
            self._last_state, self._last_push = sig, now
            self.hub.broadcast({"t": "state", **self.state(), "title": self._title()})

    def _title(self) -> str:
        try:
            return self.br.page.title()
        except PlaywrightError as err:
            logger.debug("titre indisponible: {}", err)
            return ""

    def _dispatch(self, c: dict) -> None:
        t = c.get("t")
        try:
            if t in ("mouse", "key", "text") and (not self.busy or self.handoff):
                self._input(c)
            elif t == "nav":
                self.navigate(c["url"])
            elif t == "history" and not self.busy:
                {"back": self.br.page.go_back, "forward": self.br.page.go_forward, "reload": self.br.page.reload}[
                    c["dir"]
                ](wait_until="commit")
            elif t == "settings":
                self.brain = "local" if c.get("brain") == "local" else "cloud"
                self.confirm_enabled = bool(c.get("confirm", self.confirm_enabled))
            elif t == "say":
                self._on_say(str(c.get("text", "")))
            elif t == "steps":
                self._run_steps(c["steps"])
        except Exception as err:
            logger.warning("commande {} en échec: {}", t, err)
            self.say("error", f"{type(err).__name__}: {err}")

    def _input(self, c: dict) -> None:
        page = self.br.page
        if c["t"] == "mouse":
            ty, x, y = c["type"], c.get("x", 0), c.get("y", 0)
            if ty == "move":
                page.mouse.move(x, y)
            elif ty == "down":
                page.mouse.move(x, y)
                page.mouse.down(button=BUTTONS.get(c.get("button", 0), "left"))
            elif ty == "up":
                page.mouse.up(button=BUTTONS.get(c.get("button", 0), "left"))
            elif ty == "wheel":
                page.mouse.wheel(c.get("dx", 0), c.get("dy", 0))
        elif c["t"] == "key":
            (page.keyboard.down if c["type"] == "down" else page.keyboard.up)(c["key"])
        elif c["t"] == "text":
            page.keyboard.insert_text(c["text"])

    def navigate(self, url: str) -> None:
        self.br.page.goto(normalize_url(url), wait_until="commit", timeout=30000)

    def _on_say(self, text: str) -> None:
        from . import commands

        self.say("user", text)
        threading.Thread(target=commands.plan_and_queue, args=(self, text), daemon=True).start()

    def _run_steps(self, steps: list[dict]) -> None:
        from . import commands

        self.busy, self.stop_requested = True, False
        try:
            for step in steps:
                if self.stop_requested:
                    self.say("assistant", "Arrêté.")
                    break
                self.say("assistant", commands.run_step(self, step))
        finally:
            self.busy = False


def main() -> None:
    from .session_ws import serve_forever

    load_env()
    session = Session()
    port = int(os.environ["SESSION_PORT"])
    threading.Thread(target=serve_forever, args=(session, "127.0.0.1", port), daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: session.shutdown())
    session.run()


if __name__ == "__main__":
    main()
