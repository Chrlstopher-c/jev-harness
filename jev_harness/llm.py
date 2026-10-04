"""Client LLM (API compatible OpenAI) avec rotation Groq/Cerebras: un fournisseur limité passe la main au suivant."""
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger

from .env import load_env
from .events import emit

PROVIDERS = [
    ("groq", "https://api.groq.com/openai/v1", "GROQ", "openai/gpt-oss-120b"),
    ("cerebras", "https://api.cerebras.ai/v1", "CEREBRAS", "gpt-oss-120b"),
]
DEFAULT_COOLDOWN_S = 30.0
MAX_COOLDOWN_S = 120.0
TRANSIENT_COOLDOWN_S = 10.0
MAX_WAIT_S = 25.0
MAX_TRIES = 6
DEAD_FILE = Path(__file__).resolve().parent.parent / ".state" / "llm_dead.json"
TTL_QUOTA_S = 1800
TTL_KEY_S = 86400


class LlmError(Exception):
    pass


class LlmUnavailable(LlmError):
    pass


@dataclass
class Slot:
    label: str
    base_url: str
    key: str
    model: str
    cooldown_until: float = 0.0
    dead: bool = False


def _build_slots() -> list[Slot]:
    load_env()
    per_provider: list[list[Slot]] = []
    for name, base, prefix, model in PROVIDERS:
        keys = [k.strip() for k in os.environ.get(f"{prefix}_API_KEYS", "").split(",") if k.strip()]
        chosen = os.environ.get(f"{prefix}_MODEL") or model
        per_provider.append([Slot(f"{name}#{i + 1}", base, k, chosen) for i, k in enumerate(keys)])
    width = max((len(p) for p in per_provider), default=0)
    return [p[i] for i in range(width) for p in per_provider if i < len(p)]


def _key_id(slot: Slot) -> str:
    return hashlib.sha1(slot.key.encode()).hexdigest()[:10]


def _load_dead(slots: list[Slot]) -> None:
    try:
        dead = json.loads(DEAD_FILE.read_text())
    except (OSError, ValueError):
        return
    for s in slots:
        if dead.get(_key_id(s), 0) > time.time():
            s.dead = True


def _mark_dead(slot: Slot, ttl: int) -> None:
    slot.dead = True
    try:
        DEAD_FILE.parent.mkdir(exist_ok=True)
        try:
            dead = json.loads(DEAD_FILE.read_text())
        except (OSError, ValueError):
            dead = {}
        dead[_key_id(slot)] = time.time() + ttl
        DEAD_FILE.write_text(json.dumps(dead))
    except OSError as err:
        logger.warning("état des clés non sauvegardé: {}", err)


_slots = _build_slots()
_load_dead(_slots)
_cursor = [random.randrange(len(_slots)) if _slots else 0]


def available() -> bool:
    return any(not s.dead for s in _slots)


def _pick() -> Slot | None:
    now = time.time()
    for step in range(len(_slots)):
        i = (_cursor[0] + step) % len(_slots)
        s = _slots[i]
        if not s.dead and s.cooldown_until <= now:
            _cursor[0] = i + 1
            return s
    return None


def _retry_after(resp: httpx.Response) -> float:
    try:
        return min(float(resp.headers.get("retry-after", DEFAULT_COOLDOWN_S)), MAX_COOLDOWN_S)
    except ValueError:
        return DEFAULT_COOLDOWN_S


def _call(slot: Slot, messages: list[dict], max_tokens: int, temperature: float) -> tuple[str, dict]:
    payload = {"model": slot.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
               "reasoning_effort": "low", "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {slot.key}", "User-Agent": "jev-harness/0.1"}
    try:
        r = httpx.post(f"{slot.base_url}/chat/completions", json=payload, headers=headers, timeout=40)
    except httpx.HTTPError as err:
        slot.cooldown_until = time.time() + TRANSIENT_COOLDOWN_S
        raise LlmError(f"{slot.label}: réseau ({type(err).__name__})") from err
    if r.status_code == 429:
        slot.cooldown_until = time.time() + _retry_after(r)
        raise LlmError(f"{slot.label}: limite de débit, pause {round(slot.cooldown_until - time.time())} s")
    if r.status_code in (401, 402, 403):
        _mark_dead(slot, TTL_QUOTA_S if r.status_code == 402 else TTL_KEY_S)
        reason = "quota épuisé ou paiement requis" if r.status_code == 402 else "clé refusée"
        raise LlmError(f"{slot.label}: {reason} ({r.status_code}), désactivée")
    if r.status_code == 413:
        slot.cooldown_until = time.time() + TRANSIENT_COOLDOWN_S
        raise LlmError(f"{slot.label}: requête trop volumineuse pour cette clé")
    if r.status_code >= 500:
        slot.cooldown_until = time.time() + TRANSIENT_COOLDOWN_S
        raise LlmError(f"{slot.label}: erreur serveur {r.status_code}")
    if r.status_code == 400 and "failed to generate json" in r.text.lower():
        raise LlmError(f"{slot.label}: JSON non généré (sortie trop longue ou invalide)")
    if r.status_code == 400 and "restricted" in r.text.lower():
        _mark_dead(slot, TTL_KEY_S)
        raise LlmError(f"{slot.label}: organisation restreinte, désactivée")
    if r.status_code != 200:
        raise LlmUnavailable(f"{slot.label}: requête refusée {r.status_code} {r.text[:200]}")
    body = r.json()
    return body["choices"][0]["message"]["content"] or "", body.get("usage", {})


def chat_json(system: str, user: str, max_tokens: int = 1500, temperature: float = 0.0) -> dict:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    deadline = time.time() + MAX_WAIT_S
    failures = 0
    while True:
        slot = _pick()
        if slot is None:
            live = [s.cooldown_until for s in _slots if not s.dead]
            if not live or min(live) > deadline:
                raise LlmUnavailable("aucun fournisseur LLM disponible")
            time.sleep(max(0.0, min(live) - time.time()))
            continue
        t0 = time.time()
        try:
            text, usage = _call(slot, messages, max_tokens, temperature)
        except LlmUnavailable:
            raise
        except LlmError as err:
            logger.warning("{}", err)
            emit("llm", f"{err}", failed=True, ms=round((time.time() - t0) * 1000))
            failures += 1
            if failures >= MAX_TRIES:
                raise LlmUnavailable(f"{failures} échecs LLM consécutifs: {err}") from err
            continue
        ms = round((time.time() - t0) * 1000)
        logger.info("llm {} ({} ms)", slot.label, ms)
        emit("llm", slot.label, ms=ms, provider=slot.label.split("#")[0],
             tokens=usage.get("prompt_tokens", 0), out=usage.get("completion_tokens", 0))
        return parse_json(text)


def parse_json(text: str) -> dict:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned.strip(), flags=re.M).strip()
    start, stop = cleaned.find("{"), cleaned.rfind("}")
    cleaned = cleaned[start:stop + 1] if 0 <= start < stop else cleaned
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise LlmError(f"réponse JSON invalide: {text[:200]}") from err
    if not isinstance(data, dict):
        raise LlmError("la réponse JSON n'est pas un objet")
    return data
