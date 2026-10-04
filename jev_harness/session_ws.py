"""Serveur WebSocket de la session: images vers le HUD, messages du HUD vers la session, /state en HTTP."""
import json
import threading
from http import HTTPStatus

from loguru import logger
from websockets.sync.server import ServerConnection, serve

from .hub import Hub
from .session import Session

MAX_MESSAGE_BYTES = 1 << 20


def _pump(ws: ServerConnection, hub: Hub, outbox) -> None:
    last = 0
    try:
        while True:
            frame = hub.next_frame(last, 0.05)
            if frame:
                last = frame[0]
                ws.send(frame[1])
            while not outbox.empty():
                ws.send(json.dumps(outbox.get(), ensure_ascii=False))
    except Exception:
        return


def _handler(session: Session):
    def handle(ws: ServerConnection) -> None:
        outbox = session.hub.add_client()
        threading.Thread(target=_pump, args=(ws, session.hub, outbox), daemon=True).start()
        session.hello(outbox)
        try:
            for raw in ws:
                try:
                    session.submit(json.loads(raw))
                except (ValueError, TypeError) as err:
                    logger.warning("message ignoré: {}", err)
        finally:
            session.hub.remove_client(outbox)
    return handle


def _http_state(session: Session):
    def process(conn: ServerConnection, request):
        if request.path == "/state":
            return conn.respond(HTTPStatus.OK, json.dumps(session.state()) + "\n")
        return None
    return process


def serve_forever(session: Session, host: str, port: int) -> None:
    with serve(_handler(session), host, port, max_size=MAX_MESSAGE_BYTES, process_request=_http_state(session)) as srv:
        logger.info("session à l'écoute sur {}:{}", host, port)
        srv.serve_forever()
