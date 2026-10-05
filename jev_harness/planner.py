"""Le LLM comprend la demande en langage naturel et propose des requêtes; Jev exécute le reste."""

from typing import Callable

from loguru import logger

from . import llm
from .briefs import Brief

Chat = Callable[[str, str], dict]

ANSWER_TYPES = {"number", "date", "entity", "text", "list"}
INTENTS = {"encyclopedic", "market", "live", "other"}

PLAN_SYSTEM = """You turn a user's request into a web-research brief. Reply with JSON only:
{"goal": "the request rewritten as one precise question, same language as the user",
 "answer_type": "number|date|entity|text|list",
 "intent": "encyclopedic (stable facts, history, definitions) | market (prices, offers, listings, reviews,
 comparisons) | live (weather, scores, stock, news) | other",
 "queries": ["2 to 4 web search queries, most direct first, in the language best suited to find the answer"]}
For market questions, use queries that surface shops, listings or price guides (words like "occasion", "annonces",
"tarif",
"cote", "acheter", "price", "for sale") and vary the angle between queries. Never answer the question yourself."""

REFORMULATE_SYSTEM = """A web research is stuck. You get the goal, queries already tried and sites already read.
Reply with JSON only: {"queries": ["2 or 3 NEW search queries from a different angle: other keywords, other
language, more specific or more general. Never repeat a tried query."]}"""


def _clean_queries(raw: object, exclude: list[str]) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen = {q.lower() for q in exclude}
    out = [q.strip() for q in raw if isinstance(q, str) and q.strip() and q.strip().lower() not in seen]
    return list(dict.fromkeys(out))[:4]


def plan(request: str, chat: Chat = llm.chat_json) -> Brief:
    data = chat(PLAN_SYSTEM, request)
    queries = _clean_queries(data.get("queries"), [])
    goal = data.get("goal")
    if not queries or not isinstance(goal, str) or not goal.strip():
        raise llm.LlmError(f"brief invalide: {data}")
    answer_type = data.get("answer_type") if data.get("answer_type") in ANSWER_TYPES else "text"
    logger.info("brief: {} {}", goal, queries)
    intent = data.get("intent") if data.get("intent") in INTENTS else "encyclopedic"
    return Brief(goal.strip(), queries, str(answer_type), str(intent))


def reformulate(goal: str, tried: list[str], hosts: list[str]) -> list[str]:
    user = f"Goal: {goal}\nQueries tried: {tried}\nSites already read: {hosts}"
    return _clean_queries(llm.chat_json(REFORMULATE_SYSTEM, user, temperature=0.4).get("queries"), tried)
