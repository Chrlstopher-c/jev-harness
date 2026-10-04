"""Client JevK5: lecture de probabilités d'options (choice / oui-non), jamais de génération."""
import os
import time
from dataclasses import dataclass

import httpx
from loguru import logger

from .events import emit

JEV_URL = os.environ.get("JEV_URL", "http://127.0.0.1:8090")
MAX_STATE_CHARS = 2500


@dataclass
class Decision:
    label: str
    confidence: float
    probabilities: dict[str, float]
    latency_ms: float


def _ask(state: str, question: dict) -> tuple[dict, float]:
    payload = {"state": state[:MAX_STATE_CHARS], "questions": {"q": question}}
    t0 = time.perf_counter()
    try:
        r = httpx.post(f"{JEV_URL}/v1/systemone", json=payload, timeout=120)
        r.raise_for_status()
        return r.json(), (time.perf_counter() - t0) * 1000
    except httpx.HTTPError as err:
        logger.error("appel Jev échoué: {}", err)
        raise


def _note(text: str, r: dict, rtt: float, probs: dict[str, float]) -> None:
    emit("jev", text, ms=round(rtt, 1), server=r["latency_ms"], tokens=r["usage"]["input_tokens"], probs=probs)


def choose(state: str, instructions: str, options: list[str]) -> Decision:
    r, rtt = _ask(state, {"type": "choice", "instructions": instructions, "criteria": options})
    a = r["answers"]["q"]
    probs: dict[str, float] = a["probabilities"]
    label = max(probs, key=lambda k: probs[k])
    logger.info("jev choice -> {} ({:.0%}, {} ms)", label, a["confidence"], r["latency_ms"])
    _note(f"{instructions} → {label}", r, rtt, probs)
    return Decision(label, a["confidence"], probs, rtt)


def yes_no(state: str, instructions: str) -> Decision:
    r, rtt = _ask(state, {"type": "noul", "instructions": instructions})
    a = r["answers"]["q"]
    p = float(a["noul"])
    label = "oui" if p >= 0.5 else "non"
    logger.info("jev oui/non -> {} (p={:.2f}, {} ms)", label, p, r["latency_ms"])
    _note(f"{instructions} → {label}", r, rtt, {"oui": p, "non": 1 - p})
    return Decision(label, a["confidence"], {"oui": p, "non": 1 - p}, rtt)
