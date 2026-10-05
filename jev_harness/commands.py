"""Commandes en langage naturel: le LLM propose des étapes, la session n'exécute que ce qui a été demandé."""

import json

from loguru import logger

from . import echohub, llm
from .command_tools import TOOLS, lab
from .session import Session

MAX_STEPS = 6

SYSTEM = """You control a web browser and a lab for the user, who talks to you in French. Reply JSON only:
{"reply": "one short sentence in French saying what you will do, or a question if the request is ambiguous",
 "steps": [{"tool": "...", "args": {...}}]}
Do ONLY what the user asked, nothing more. Chain several steps only when asked ("create a brief then run it").
If the request is ambiguous or missing information, ask in "reply" and return no steps.
When the user asks for an action on a page (fill and send a form, click, search on a site), do it with the act tool:
sensitive actions (sending, paying, deleting) are confirmed by the user in the interface, and passwords are typed by
the user, so never refuse them yourself. If a password is mentioned but not given, still call act: the user types it
himself. If the user asks you to play a game for them, call play_game (never refuse yourself: unavailable features are
reported by the tool). To run the brief you just created, use run_brief with name "last". For "go to X and do Y",
chain navigate then act. Tools:
- navigate {url}: open a URL or domain
- search_web {query}: open web search results for a query
- back {} / forward {} / reload {}
- scroll {direction: "up"|"down", amount: pixels, default 600}
- answer {question}: research a factual question with the Jev + LLM pipeline and give the answer
- run_brief {name}: run an existing brief (by title or id)
- create_brief {request, backend: "cloud"|"local"}: generate and save a brief from a request
- list_briefs {}: list the saved briefs
- jev {action: "load"|"unload"}: load or unload the JevK5 model
- local_model {action: "load"|"unload", name}: load (by name) or unload the local EchoHub model
- act {task}: do an interaction task on the CURRENT page with real clicks and typing (search on a site, fill a form,
  click through...)
- play_game {game, instructions}: play chess for the user on the local board (only chess is available)"""


def run_step(session: Session, step: dict) -> str:
    try:
        return TOOLS[step["tool"]](session, step.get("args") or {})
    except Exception as err:
        logger.exception("étape {} en échec", step)
        return f"Échec de « {step.get('tool')} » : {err}"


def _context(session: Session) -> str:
    try:
        st, briefs = lab("GET", "/api/status"), lab("GET", "/api/briefs")["briefs"]
        local = (st.get("echohub") or {}).get("state", "indisponible")
        names = "; ".join(f"{b['id']} = {b['title']}" for b in briefs[:20])
        url = session.state().get("url")
        return f"Page : {url} | JevK5 prêt : {st['jevk5']['ready']} | modèle local : {local} | briefs : {names}"
    except Exception as err:
        return f"(contexte indisponible: {err})"


def _chat(brain: str):
    if brain == "local" and (echohub.state().get("etat") == "pret"):
        return echohub.chat_json
    return llm.chat_json


def plan_and_queue(session: Session, text: str) -> None:
    try:
        data = _chat(session.brain)(SYSTEM, f"{_context(session)}\n\nUser: {text}")
    except llm.LlmError as err:
        session.say("error", f"Je n'ai pas pu interpréter la demande : {err}")
        return
    steps = [s for s in (data.get("steps") or [])[:MAX_STEPS] if isinstance(s, dict) and s.get("tool") in TOOLS]
    if data.get("reply"):
        session.say("assistant", str(data["reply"]))
    if steps:
        session.submit({"t": "steps", "steps": steps})
    logger.info("commande « {} » → {}", text, json.dumps(steps, ensure_ascii=False))
