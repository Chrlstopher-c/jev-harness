"""Recherche ouverte: requêtes -> résultats de plusieurs moteurs mélangés -> Jev choisit, lit, juge; le LLM vérifie."""
import re
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from urllib.parse import urlparse

from loguru import logger

from . import jev, llm, planner, wikipedia
from .answer import NUMERIC_Q, Formulated, extract_llm, formulate
from .browser import Browser, Hit
from . import events
from .events import span

MAX_PAGES = 8
MAX_RESULTS_FOR_JEV = 8
TITLE_CHARS = 60
SNIPPET_CHARS = 90
JUDGED = 3
KEEP_CONTEXT = 2
MARKET_CONTEXT_CHUNKS = 6
EARLY_STOP = 0.95
MAX_REFORMULATIONS = 2
PAGES_PER_QUERY = 3
MAX_PER_HOST = 2
CONFIDENT = 0.8
NONE_OPTION = "aucun de ces résultats"
GIVE_UP_PROB = 0.85
MIN_PAGE_CHARS = 200
JUDGE_ASK = {"market": "Does the passage show prices or offers relevant to the question?",
             "live": "Does the passage give the current figure asked for in the question?"}


@dataclass
class Found:
    url: str
    passage: str
    score: float
    value: str | None = None
    quote: str | None = None
    verified: bool = False
    context: str = ""


@dataclass
class Answer:
    url: str
    value: str | None
    sentence: str
    confidence: float
    certain: bool
    pages_read: int
    verified: bool


@dataclass
class State:
    answer_type: str = "text"
    intent: str = "encyclopedic"
    host_counts: dict[str, int] = field(default_factory=dict)
    visited: set[str] = field(default_factory=set)
    tried: list[str] = field(default_factory=list)
    best: Found | None = None
    pages: int = 0


def host(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def gather(br: Browser, query: str, seen: set[str], with_wikipedia: bool = True) -> list[Hit]:
    with ThreadPoolExecutor(max_workers=1) as pool:
        wiki = pool.submit(events.bind(wikipedia.search), query) if with_wikipedia else None
        try:
            bing = br.bing_search(query)
        except Exception as err:
            logger.error("Bing en échec: {}", err)
            bing = []
        lists = [bing, wiki.result() if wiki else []]
    mixed = [h for pair in zip_longest(*lists) for h in pair if h and h.url not in seen]
    return list({h.url: h for h in mixed}.values())


def choose_hit(goal: str, hits: list[Hit]) -> Hit | None:
    shown = hits[:MAX_RESULTS_FOR_JEV]
    with span("choose", f"Choisir la page la plus prometteuse parmi {len(shown)} résultats") as sp:
        labels = [f"{i + 1}. {h.title[:TITLE_CHARS]} ({host(h.url)})" for i, h in enumerate(shown)] + [NONE_OPTION]
        state = f"Goal: {goal}\n" + "\n".join(f"{i + 1}. {h.snippet[:SNIPPET_CHARS]}" for i, h in enumerate(shown))
        d = jev.choose(state, "Which search result is most likely to contain the answer to the goal?", labels)
        if d.label == NONE_OPTION and d.probabilities[NONE_OPTION] >= GIVE_UP_PROB:
            sp["detail"], sp["status"] = "Jev ne voit aucun résultat convaincant", "miss"
            return None
        best = max((k for k in d.probabilities if k != NONE_OPTION), key=lambda k: d.probabilities[k])
        hit = shown[labels.index(best)]
        sp["detail"] = f"Jev choisit : {hit.title} ({host(hit.url)})"
        return hit


def rank(goal: str, passages: list[str]) -> list[str]:
    terms = {w for w in re.findall(r"\w+", goal.lower()) if len(w) > 3}
    numeric = bool(NUMERIC_Q.search(goal))

    def score(p: str) -> float:
        low = p.lower()
        return sum(t in low for t in terms) + (0.5 if numeric and re.search(r"\d", p) else 0)

    return sorted(passages, key=lambda p: -score(p))


def find_in_page(goal: str, br: Browser, intent: str = "encyclopedic") -> Found | None:
    with span("read", "Lire la page et chercher la réponse") as sp:
        passages = br.passages()
        if sum(len(p) for p in passages) < MIN_PAGE_CHARS:
            sp["status"], sp["detail"] = "miss", "Page vide ou bloquée par une protection anti-robot"
            return None
        candidates = rank(goal, passages)[:JUDGED]
        scored: list[tuple[str, float]] = []
        for passage in candidates:
            ask = JUDGE_ASK.get(intent, "Does the passage directly answer the question?")
            d = jev.yes_no(f"Question: {goal}\nPassage:\n{passage}", ask)
            scored.append((passage, d.probabilities["oui"]))
            if scored[-1][1] >= EARLY_STOP:
                break
        scored.sort(key=lambda x: -x[1])
        top = scored[0][1] if scored else 0.0
        sp["detail"] = f"{len(scored)} extraits jugés par Jev · meilleur score {round(top * 100)} %"
        sp["status"] = "ok" if top >= 0.5 else "miss"
        if top < 0.5:
            return None
        wide = rank(goal, passages)[:MARKET_CONTEXT_CHUNKS] if intent == "market" else [p for p, _ in scored[:KEEP_CONTEXT]]
        ctx = "\n---\n".join(wide)
        return Found(br.page.url, scored[0][0], top, context=ctx)


def confirm(goal: str, st: State, found: Found) -> bool | None:
    """True = LLM confirme, False = LLM ne voit pas la réponse, None = LLM indisponible."""
    if not llm.available():
        return None
    with span("verify", "Faire vérifier la réponse par le LLM") as sp:
        try:
            f = extract_llm(goal, st.answer_type, found.context or found.passage, st.intent)
        except llm.LlmError as err:
            logger.warning("vérification LLM sautée: {}", err)
            sp["status"], sp["detail"] = "partial", "LLM indisponible ou réponse non fiable, vérification sautée"
            return None
        if f is None:
            sp["status"], sp["detail"] = "miss", "Le LLM ne trouve pas la réponse dans ce passage"
            return False
        found.value, found.quote, found.verified = f.value, f.sentence, True
        sp["detail"] = f.value or ""
        return True


def visit(goal: str, br: Browser, hit: Hit, st: State) -> Found | None:
    with span("page", f"Page n°{st.pages} : {host(hit.url)}", url=hit.url) as pg:
        with span("load", "Ouvrir la page dans le navigateur") as ld:
            try:
                br.open(hit.url)
            except Exception:
                ld["status"], ld["detail"] = "error", "Page inaccessible"
                pg["status"], pg["detail"] = "error", "Page inaccessible, on passe à la suivante"
                return None
        found = find_in_page(goal, br, st.intent)
        verdict = confirm(goal, st, found) if found else None
        if verdict is False:
            pg["status"], pg["detail"] = "miss", "Jev y voyait une réponse, le LLM non : on continue"
            return None
        if found and (verdict or found.score >= CONFIDENT):
            pg["detail"] = "Réponse trouvée et vérifiée" if verdict else "Réponse trouvée avec confiance"
        elif found:
            pg["status"], pg["detail"] = "partial", "Réponse possible mais peu sûre"
        else:
            pg["status"], pg["detail"] = "miss", "Pas de réponse nette sur cette page"
        return found


def search_round(goal: str, query: str, br: Browser, st: State, max_pages: int) -> Found | None:
    with span("gather", "Interroger Bing" + (" et Wikipédia (en parallèle)" if st.intent == "encyclopedic" else "")) as g:
        hits = gather(br, query, st.visited, st.intent == "encyclopedic")
        g["detail"] = f"{len(hits)} résultats trouvés"
    taken = 0
    while hits and st.pages < max_pages and taken < PAGES_PER_QUERY:
        hits = [h for h in hits if st.host_counts.get(host(h.url), 0) < MAX_PER_HOST]
        hit = choose_hit(goal, hits) if hits else None
        if hit is None:
            return None
        hits.remove(hit)
        st.visited.add(hit.url)
        st.host_counts[host(hit.url)] = st.host_counts.get(host(hit.url), 0) + 1
        st.pages += 1
        taken += 1
        found = visit(goal, br, hit, st)
        if found and (found.verified or found.score >= CONFIDENT):
            return found
        if found and (st.best is None or found.score > st.best.score):
            st.best = found
    return None


def formulate_final(goal: str, st: State, found: Found) -> Formulated | None:
    if found.value:
        return Formulated(found.quote or "", found.value)
    if llm.available():
        try:
            f = extract_llm(goal, st.answer_type, found.context or found.passage, st.intent)
            found.verified = f is not None
            return f
        except llm.LlmError as err:
            logger.warning("extraction LLM sautée: {}", err)
    return formulate(goal, found.passage)


def finalize(goal: str, st: State, found: Found, certain: bool) -> Answer | None:
    with span("extract", "Formuler la réponse finale") as sp:
        f = formulate_final(goal, st, found)
        if f is None:
            sp["status"], sp["detail"] = "miss", "Le LLM ne voit de réponse dans aucun candidat"
            return None
        sp["detail"] = f.value or f.sentence[:120]
        return Answer(found.url, f.value, f.sentence, found.score, certain, st.pages, found.verified)


def more_queries(goal: str, st: State) -> list[str]:
    if not llm.available():
        return []
    with span("reformulate", "Imaginer d'autres recherches (LLM)") as sp:
        try:
            qs = planner.reformulate(goal, st.tried, [host(u) for u in st.visited])
        except llm.LlmError as err:
            sp["status"], sp["detail"] = "error", f"LLM indisponible: {err}"
            return []
        sp["detail"] = " · ".join(qs) or "Aucune idée nouvelle"
        return qs


def research(br: Browser, goal: str, queries: list[str], answer_type: str = "text",
             max_pages: int = MAX_PAGES, intent: str = "encyclopedic") -> Answer | None:
    st = State(answer_type, intent)
    queue, found, rounds = list(queries), None, 0
    while queue and st.pages < max_pages:
        query = queue.pop(0)
        st.tried.append(query)
        with span("search", f"Recherche n°{len(st.tried)} : « {query} »") as sr:
            found = search_round(goal, query, br, st, max_pages)
            sr["status"] = "ok" if found else "miss"
            sr["detail"] = "Réponse trouvée" if found else "Rien de concluant"
        if found:
            break
        if not queue and rounds < MAX_REFORMULATIONS and st.pages < max_pages:
            rounds += 1
            queue = more_queries(goal, st)
    chosen = found or st.best
    return finalize(goal, st, chosen, found is not None) if chosen else None
