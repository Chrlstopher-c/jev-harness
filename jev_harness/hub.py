"""Distribution aux clients WebSocket: dernière image seulement (les retardataires sautent) + messages JSON."""

import queue
import threading


class Hub:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._seq = 0
        self._frame = b""
        self._lock = threading.Lock()
        self._clients: set[queue.Queue] = set()
        self.meta: dict = {}

    def publish_frame(self, data: bytes, meta: dict) -> None:
        with self._cond:
            self._frame, self.meta = data, meta
            self._seq += 1
            self._cond.notify_all()

    def next_frame(self, last: int, timeout: float = 0.1) -> tuple[int, bytes] | None:
        with self._cond:
            if self._seq == last and not self._cond.wait(timeout):
                return None
            return (self._seq, self._frame) if self._seq != last else None

    def add_client(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._clients.add(q)
        return q

    def remove_client(self, q: queue.Queue) -> None:
        with self._lock:
            self._clients.discard(q)

    def broadcast(self, msg: dict) -> None:
        with self._lock:
            for q in self._clients:
                q.put(msg)
