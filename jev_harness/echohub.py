"""Modèle local servi par EchoHub: état et génération JSON (flux SSE agrégé)."""
import json
import os

import httpx
from loguru import logger

from . import llm

GENERATE_TIMEOUT_S = 900
MAX_TOKENS = 8000


def _base() -> str:
    url = os.environ.get("ECHOHUB_URL", "")
    if not url:
        raise llm.LlmUnavailable("ECHOHUB_URL n'est pas défini (voir .env.example)")
    return url.rstrip("/")


def state() -> dict:
    try:
        return httpx.get(f"{_base()}/inference/etat", timeout=5).json()
    except httpx.HTTPError as err:
        raise llm.LlmUnavailable(f"EchoHub injoignable: {err}") from err


def _tokens(resp: httpx.Response) -> str:
    out: list[str] = []
    for line in resp.iter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
        event = json.loads(payload)
        if event.get("type") == "erreur":
            raise llm.LlmError(f"EchoHub: {event.get('message', event)}")
        if event.get("type") == "token":
            out.append(event.get("contenu", ""))
    return "".join(out)


def chat_json(system: str, user: str, max_tokens: int = MAX_TOKENS) -> dict:
    st = state()
    if st.get("etat") != "pret":
        raise llm.LlmUnavailable(f"aucun modèle local prêt (état : {st.get('etat')}) : charge-en un d'abord")
    body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.2, "max_tokens": max_tokens}}
    logger.info("génération locale avec {}", st.get("modele"))
    try:
        with httpx.stream("POST", f"{_base()}/inference/generer", json=body, timeout=GENERATE_TIMEOUT_S) as resp:
            if resp.status_code != 200:
                raise llm.LlmUnavailable(f"EchoHub a refusé la génération ({resp.status_code})")
            text = _tokens(resp)
    except httpx.HTTPError as err:
        raise llm.LlmUnavailable(f"EchoHub injoignable: {err}") from err
    return llm.parse_json(text)
