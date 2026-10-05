"""Outils exécutables par le routeur de commandes (navigation, recherche, briefs, moteurs, actions, jeux)."""

import os
import time
from typing import Callable

import httpx
from loguru import logger

from . import events, runner
from .briefs import get as get_brief
from .session import SEARCH_URL, Session

POLL_S = 2.0
TIMEOUT_S = 15

Tool = Callable[[Session, dict], str]


def lab(method: str, path: str, body: dict | None = None) -> dict:
    url = os.environ["LAB_URL"].rstrip("/") + path
    try:
        r = httpx.request(method, url, json=body, timeout=TIMEOUT_S)
        data = r.json()
    except (httpx.HTTPError, ValueError) as err:
        logger.error("lab {} {} injoignable: {}", method, path, err)
        raise RuntimeError(f"lab injoignable ({path}): {err}") from err
    if r.status_code >= 400:
        raise RuntimeError(data.get("error", f"HTTP {r.status_code}"))
    return data


def _wait(session: Session, check: Callable[[], str | None], timeout_s: float) -> str:
    end = time.time() + timeout_s
    while time.time() < end and not session.stop_requested:
        done = check()
        if done is not None:
            return done
        session.br.page.wait_for_timeout(int(POLL_S * 1000))
    return "interrompu ou délai dépassé"


def _page(session: Session):
    return session.br.page


def t_navigate(s: Session, a: dict) -> str:
    s.navigate(str(a.get("url", "")))
    return f"Page ouverte : {_page(s).url}"


def t_search(s: Session, a: dict) -> str:
    from urllib.parse import quote_plus

    s.navigate(SEARCH_URL + quote_plus(str(a.get("query", ""))))
    return f"Recherche lancée : {a.get('query')}"


def t_history(direction: str) -> Tool:
    def run(s: Session, _a: dict) -> str:
        {"back": _page(s).go_back, "forward": _page(s).go_forward, "reload": _page(s).reload}[direction](
            wait_until="commit"
        )
        return {"back": "Page précédente.", "forward": "Page suivante.", "reload": "Page rechargée."}[direction]

    return run


def t_scroll(s: Session, a: dict) -> str:
    dy = int(a.get("amount", 600)) * (-1 if a.get("direction") == "up" else 1)
    _page(s).mouse.wheel(0, dy)
    return "Défilement effectué."


def _jev_ready() -> bool:
    return bool(lab("GET", "/api/status")["jevk5"]["ready"])


def _run_and_report(s: Session, request: str, fixed: list[str], answer_type: str, intent: str = "encyclopedic") -> str:
    if not _jev_ready():
        return "JevK5 n'est pas chargé : dis « charge Jev » (après avoir déchargé le modèle local s'il est actif)."
    events.reset()
    t0 = time.time()
    try:
        result = runner.execute(request, fixed, answer_type, shared=s.br, intent=intent)
    except Exception:
        logger.exception("exécution du brief en échec")
        raise
    finally:
        events.archive()
    took = round(time.time() - t0, 1)
    if hasattr(result, "sentence"):
        flag = "" if result.certain else " (réponse incertaine)"
        return f"{result.value or result.sentence}{flag} · source : {result.url} · {took} s"
    return (
        "Rapport d'analyse terminé, il est dans l'onglet Harnais." if result else f"Aucune réponse trouvée ({took} s)."
    )


def t_answer(s: Session, a: dict) -> str:
    return _run_and_report(s, str(a.get("question", "")), [], "text")


def _find_brief(name: str) -> dict | None:
    rec = get_brief(name)
    if rec:
        return rec
    low = name.lower()
    return next((b for b in lab("GET", "/api/briefs")["briefs"] if low in b["title"].lower() or low in b["id"]), None)


def t_run_brief(s: Session, a: dict) -> str:
    name = str(a.get("name", ""))
    rec = s.last_brief if name.lower() in ("last", "latest", "dernier", "") and s.last_brief else _find_brief(name)
    if rec is None:
        return f"Brief introuvable : {a.get('name')}. Dis « liste les briefs » pour voir les noms."
    return _run_and_report(
        s,
        rec["request"],
        list(rec.get("queries", [])),
        rec.get("answer_type", "text"),
        rec.get("intent", "encyclopedic"),
    )


def t_create_brief(s: Session, a: dict) -> str:
    backend = "local" if a.get("backend") == "local" else "cloud"
    job = lab("POST", "/api/briefs/generate", {"request": a.get("request", ""), "backend": backend})["job"]

    def check() -> str | None:
        j = lab("GET", f"/api/briefs/job?id={job}")
        if j["state"] == "error":
            return f"Échec de la génération : {j['error']}"
        b = j.get("brief")
        if b:
            s.last_brief = b
        return f"Brief créé : « {b['title']} » ({len(b['queries'])} requêtes)" if j["state"] == "done" else None

    return _wait(s, check, 900)


def t_list_briefs(_s: Session, _a: dict) -> str:
    return "Briefs : " + " · ".join(b["title"] for b in lab("GET", "/api/briefs")["briefs"])


def t_jev(s: Session, a: dict) -> str:
    load = a.get("action") == "load"
    lab("POST", "/api/jevk5/start" if load else "/api/jevk5/stop", {})
    if not load:
        return "JevK5 déchargé."
    return "JevK5 chargé." if _wait(s, lambda: "ok" if _jev_ready() else None, 180) == "ok" else "JevK5 ne répond pas."


def _model_id(name: str) -> str:
    models = lab("GET", "/api/echohub/models")["models"]
    hit = next((m for m in models if name.lower() in m["name"].lower() or name.lower() in m["id"].lower()), None)
    if hit is None:
        raise RuntimeError(f"Modèle inconnu : {name}. Exemples : " + ", ".join(m["name"] for m in models[:5]))
    return hit["id"]


def t_local_model(s: Session, a: dict) -> str:
    if a.get("action") != "load":
        lab("POST", "/api/echohub/unload", {})
        return "Modèle local déchargé."
    lab("POST", "/api/echohub/load", {"id": _model_id(str(a.get("name", "")))})

    def check() -> str | None:
        st = (lab("GET", "/api/status").get("echohub") or {}).get("state")
        return "ok" if st == "pret" else "échec" if st == "echoue" else None

    return "Modèle local prêt." if _wait(s, check, 900) == "ok" else "Le chargement du modèle local a échoué ou expiré."


def t_act(s: Session, a: dict) -> str:
    task = str(a.get("task", "")).strip()
    if not task:
        return "Dis-moi ce que je dois faire dans la page."
    if not _jev_ready():
        return "JevK5 n'est pas chargé : dis « charge Jev » (après avoir déchargé le modèle local s'il est actif)."
    from .agent import Agent

    events.reset()
    with events.span("request", f"Agir : {task}") as root:
        msg = Agent(s, task).run()
        root["status"] = "ok" if msg.startswith("Tâche terminée") else "partial"
        root["detail"] = msg
    events.archive()
    return msg


def t_play(s: Session, a: dict) -> str:
    game = str(a.get("game", "")).lower()
    if game and not any(k in game for k in ("chess", "écheca", "echec")):
        return f"Je ne sais pas encore jouer à « {a.get('game')} » : seuls les échecs sont disponibles."
    if not _jev_ready():
        return "JevK5 n'est pas chargé : dis « charge Jev » (après avoir déchargé le modèle local s'il est actif)."
    from .chess_adapters import detect
    from .chess_agent import ChessAgent

    if detect(_page(s)) is None:
        s.navigate(os.environ["LAB_URL"].rstrip("/") + "/chess/")
        s.br.page.wait_for_selector("#board[data-fen]", timeout=10000)
    adapter = detect(_page(s))
    if adapter is None:
        return "Je ne reconnais pas de plateau d'échecs sur cette page."
    events.reset()
    with events.span("request", "Partie d'échecs") as root:
        msg = ChessAgent(s, adapter, safety=True).play()
        root["status"], root["detail"] = "ok", msg
    events.archive()
    return msg


TOOLS: dict[str, Tool] = {
    "navigate": t_navigate,
    "search_web": t_search,
    "back": t_history("back"),
    "forward": t_history("forward"),
    "reload": t_history("reload"),
    "scroll": t_scroll,
    "answer": t_answer,
    "run_brief": t_run_brief,
    "create_brief": t_create_brief,
    "act": t_act,
    "list_briefs": t_list_briefs,
    "jev": t_jev,
    "local_model": t_local_model,
    "play_game": t_play,
}
