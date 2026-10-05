"""CLI: génère un brief depuis une demande en langage naturel, JSON sur stdout (le banc l'enregistre)."""

import argparse
import json
import sys

from loguru import logger

from . import echohub, llm, planner
from .site_report import site_url

TITLE_CHARS = 70


def generate(request: str, backend: str) -> dict:
    if site_url(request):
        return {"title": request[:TITLE_CHARS], "request": request, "queries": [], "answer_type": "text"}
    chat = echohub.chat_json if backend == "local" else llm.chat_json
    brief = planner.plan(request, chat)
    return {
        "title": brief.goal[:TITLE_CHARS],
        "request": brief.goal,
        "queries": brief.queries,
        "answer_type": brief.answer_type,
        "intent": brief.intent,
    }


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--backend", choices=["cloud", "local"], default="cloud")
    args = ap.parse_args()
    try:
        print(json.dumps(generate(args.request, args.backend), ensure_ascii=False))
    except llm.LlmError as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))
        sys.exit(1)
