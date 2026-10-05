"""Exécution d'un test complet (recherche ou analyse de site), dans un navigateur neuf ou déjà ouvert."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext

from loguru import logger

from . import events, llm, planner
from .briefs import Brief, from_goal
from .browser import Browser
from .research import Answer, research
from .site_report import analyse_site, site_url


def plan_brief(request: str) -> Brief:
    if not llm.available():
        return from_goal(request)
    with events.span("plan", "Comprendre la demande (LLM)") as sp:
        try:
            brief = planner.plan(request)
        except llm.LlmError as err:
            sp["status"], sp["detail"] = "partial", f"LLM indisponible, requêtes simples utilisées ({err})"
            return from_goal(request)
        sp["detail"] = " · ".join(brief.queries)
        return brief


def _search(request: str, fixed: list[str], answer_type: str, shared: Browser | None, intent: str) -> Answer | None:
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(events.bind(plan_brief), request) if not fixed else None
        with nullcontext(shared) if shared else Browser() as br:
            brief = pending.result() if pending else Brief(request, fixed, answer_type, intent)
            return research(br, brief.goal, brief.queries, brief.answer_type, intent=brief.intent)


def execute(
    request: str, fixed: list[str], answer_type: str, shared: Browser | None = None, intent: str = "encyclopedic"
) -> Answer | None | bool:
    """Un test dans le span `request`. `shared` = navigateur déjà ouvert (session interactive).

    Rend l'Answer d'une recherche, True/False pour une analyse de site, None si rien n'est trouvé.
    """
    with events.span("request", request) as root:
        try:
            if not fixed and site_url(request):
                ok = analyse_site(request, site_url(request) or "", shared)
                root["status"] = "ok" if ok else "error"
                return ok
            ans = _search(request, fixed, answer_type, shared, intent)
        except Exception as err:
            logger.exception("run échoué")
            root["status"], root["detail"] = "error", f"Erreur: {err}"
            return None
        root["status"] = "ok" if ans and ans.certain else "partial" if ans else "miss"
        if ans:
            events.emit(
                "answer",
                ans.sentence,
                value=ans.value,
                url=ans.url,
                confidence=ans.confidence,
                certain=ans.certain,
                pages=ans.pages_read,
                verified=ans.verified,
            )
        else:
            root["detail"] = "Aucune réponse trouvée"
        return ans
