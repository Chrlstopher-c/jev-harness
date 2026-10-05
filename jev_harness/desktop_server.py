"""Service du bureau virtuel: démarre la pile et expose une API de contrôle JSON sur localhost."""

import json
import os
import signal
import threading
import time
from collections import deque
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from loguru import logger

from .desktop_ctl import DesktopCtl, DesktopError
from .desktop_stack import Stack, StackError
from .env import load_env

MAX_BODY = 64 * 1024
EVENTS: deque[dict] = deque(maxlen=200)


def note(kind: str, detail: str) -> None:
    EVENTS.append({"t": round(time.time(), 2), "kind": kind, "detail": detail})


def _actions(ctl: DesktopCtl) -> dict:
    return {
        "/launch": lambda b: ctl.launch(str(b["cmd"])),
        "/click": lambda b: ctl.click(int(b["x"]), int(b["y"]), str(b.get("button", "left"))),
        "/move": lambda b: ctl.move(int(b["x"]), int(b["y"])),
        "/type": lambda b: ctl.type_text(str(b["text"])),
        "/key": lambda b: ctl.press(str(b["keys"])),
        "/close": lambda b: ctl.close_window(int(b["id"])),
        "/focus": lambda b: ctl.focus_window(int(b["id"])),
    }


class Handler(BaseHTTPRequestHandler):
    def __init__(self, ctl: DesktopCtl, actions: dict, *args: object) -> None:
        self.ctl, self.actions = ctl, actions
        super().__init__(*args)

    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug("http " + fmt, *args)

    def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: object) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode())

    def do_GET(self) -> None:
        try:
            if self.path == "/state":
                self._json(200, self.ctl.state())
            elif self.path == "/events":
                self._json(200, {"events": list(EVENTS)})
            elif self.path.split("?")[0] == "/shot.jpg":
                query = parse_qs(urlparse(self.path).query)
                self._send(200, self.ctl.screenshot(float(query.get("scale", ["1"])[0])), "image/jpeg")
            else:
                self._json(404, {"error": "inconnu"})
        except (DesktopError, ValueError) as err:
            self._json(502, {"error": str(err)})
        except Exception as err:  # noqa: BLE001 - jamais de connexion coupée sans réponse
            logger.exception("GET {} en échec", self.path)
            self._json(500, {"error": f"erreur interne: {err}"})

    def do_POST(self) -> None:
        action = self.actions.get(self.path)
        if action is None:
            self._json(404, {"error": "inconnu"})
            return
        try:
            size = min(int(self.headers.get("content-length", 0)), MAX_BODY)
            body = json.loads(self.rfile.read(size) or b"{}")
            action(body)
            note(self.path.strip("/"), json.dumps(body, ensure_ascii=False)[:160])
            self._json(200, {"ok": True})
        except (KeyError, ValueError, TypeError) as err:
            self._json(HTTPStatus.BAD_REQUEST, {"error": f"requête invalide: {err}"})
        except DesktopError as err:
            self._json(502, {"error": str(err)})
        except Exception as err:  # noqa: BLE001 - jamais de connexion coupée sans réponse
            logger.exception("POST {} en échec", self.path)
            self._json(500, {"error": f"erreur interne: {err}"})


def watch(stack: Stack, server: ThreadingHTTPServer, interval_s: float = 2.0) -> None:
    """Arrête le service si un composant de la pile meurt: le labo voit « arrêté » au lieu d'un bureau fantôme."""
    while True:
        time.sleep(interval_s)
        if not stack.alive():
            logger.error("un composant du bureau virtuel s'est arrêté: arrêt du service")
            server.shutdown()
            return


def main() -> None:
    load_env()
    stack = Stack(int(os.environ["DESKTOP_VNC_PORT"]), int(os.environ["DESKTOP_WS_PORT"]), Path("run/desktop"))
    try:
        stack.start()
    except StackError:
        raise SystemExit(1) from None
    ctl = DesktopCtl(stack)
    server = ThreadingHTTPServer(("127.0.0.1", int(os.environ["DESKTOP_PORT"])), partial(Handler, ctl, _actions(ctl)))
    stop = threading.Event()

    def shutdown(*_: object) -> None:
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    threading.Thread(target=watch, args=(stack, server), daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    note("start", "bureau virtuel démarré")
    try:
        server.serve_forever()
    finally:
        stack.stop()
        logger.info("bureau virtuel arrêté")


if __name__ == "__main__":
    main()
