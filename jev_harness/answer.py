"""Formuler la réponse finale: Jev choisit la phrase qui répond, puis la valeur chiffrée si elle existe."""

import re
from dataclasses import dataclass

from loguru import logger

from . import jev, llm

MAX_SENTENCES = 8
EXTRACT_TRIES = 2
MARKET_RULE = """
This is a price/offer question: do not pick one random listing. Give the range or typical price actually shown
(for example "de 112 000 € à 389 900 € (annonces d'occasion)" or "à partir de 135 000 €"), saying what it applies to
(new, used, listings). Copy every figure exactly as written in the passage."""
_NUMBER = r"\d[\d\s\u00a0\u202f.,]*\d(?:[\s\u00a0]?(?:€|%|km|m|habitants|millions|milliards))?|\d"
VALUE = re.compile(rf"(?<![A-Za-zÀ-ÿ\d])(?:{_NUMBER})(?![A-Za-zÀ-ÿ\d])")


@dataclass
class Formulated:
    sentence: str
    value: str | None


NUMERIC_Q = re.compile(
    r"prix|hauteur|population|combien|nombre|taille|âge|année|date|quand|distance|poids|cours|coût", re.I
)


def _terms(goal: str) -> set[str]:
    return {w for w in re.findall(r"\w+", goal.lower()) if len(w) > 3}


def _candidates(passage: str) -> list[str]:
    lines = [ln.strip() for ln in passage.split("\n") if ln.strip()]
    pairs = [f"{x} {y}" for x, y in zip(lines, lines[1:])]
    sentences = [s.strip() for ln in lines for s in re.split(r"(?<=[.!?])\s+", ln)]
    return list(dict.fromkeys(sentences + pairs))


def _sentences(goal: str, passage: str) -> list[str]:
    good = [s for s in _candidates(passage) if 15 <= len(s) <= 400]
    if NUMERIC_Q.search(goal):
        good = [s for s in good if _values(s)] or good
    terms = _terms(goal)
    ranked = sorted(good, key=lambda s: -sum(t in s.lower() for t in terms))
    return ranked[:MAX_SENTENCES]


def _values(sentence: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in VALUE.finditer(sentence):
        v = re.sub(r"\s+", " ", m.group(0)).strip(" .,")
        if v:
            seen[v] = None
    return list(seen)


def formulate(goal: str, passage: str) -> Formulated:
    passage = re.sub(r"\[\w{1,3}\]", "", passage)
    sentences = _sentences(goal, passage)
    if not sentences:
        return Formulated(passage.strip()[:300], None)
    labels = [f"{i + 1}. {s[:140]}" for i, s in enumerate(sentences)]
    d = jev.choose(f"Question: {goal}\nPassage:\n{passage[:1500]}", "Which sentence answers the question best?", labels)
    sentence = sentences[labels.index(d.label)]
    values = _values(sentence)
    if len(values) > 1:
        d2 = jev.choose(f"Question: {goal}\nSentence: {sentence}", "Which value answers the question?", values)
        return Formulated(sentence, d2.label)
    return Formulated(sentence, values[0] if values else None)


EXTRACT_SYSTEM = """Extract the answer to the question from the passage ONLY. Never use outside knowledge.
Reply with JSON only: {"found": true, "value": "concise answer: number with unit, name, date...",
"quote": "the exact sentence copied verbatim from the passage that supports it"}
Write the value in the language of the passage, with figures and units exactly as written there (never translate).
Never use ellipses in the quote: copy complete lines or sentences only.
If the passage does not directly answer the question, reply {"found": false}."""


def _squash(text: str) -> str:
    return re.sub(r"[\s\u00a0\u202f]+", "", re.sub(r"\[\w{1,3}\]", "", text)).lower()


def extract_llm(goal: str, answer_type: str, passage: str, intent: str = "encyclopedic") -> Formulated | None:
    """None = le LLM ne voit pas la réponse. LlmError si indisponible ou si la citation n'est pas dans le passage."""
    for attempt in range(EXTRACT_TRIES):
        try:
            return _extract_once(goal, answer_type, passage, attempt, intent)
        except llm.LlmUnavailable:
            raise
        except llm.LlmError as err:
            if attempt == EXTRACT_TRIES - 1:
                raise
            logger.warning("extraction LLM à reprendre: {}", err)
    return None


def _extract_once(goal: str, answer_type: str, passage: str, attempt: int, intent: str) -> Formulated | None:
    strict = " Copy the quote lines EXACTLY as they appear in the passage." if attempt else ""
    data = llm.chat_json(
        EXTRACT_SYSTEM + MARKET_RULE * (intent == "market") + strict,
        f"Question: {goal}\nExpected type: {answer_type}\nPassages:\n{passage[:4000]}",
    )
    if data.get("found") is not True:
        return None
    value, quote = str(data.get("value", "")).strip(), str(data.get("quote", "")).strip()
    flat = _squash(passage)
    lines = [ln for ln in re.split(r"\n|\.\.\.|…", quote) if ln.strip()]
    numbers = re.findall(r"\d[\d\s\u00a0\u202f.,]*\d|\d", value)
    words = [x for x in re.split(r"\s*(?:,\s+|;|\bet\b|\band\b|/)\s*", value) if x and not re.search(r"\d", x)]
    value_ok = all(_squash(n) in flat for n in numbers) and all(_squash(w) in flat for w in words)
    grounded = bool(value and lines) and all(_squash(ln) in flat for ln in lines) and value_ok
    if not grounded:
        raise llm.LlmError("réponse du LLM non ancrée dans le passage")
    return Formulated(quote, value)
