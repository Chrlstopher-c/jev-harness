"""Analyse d'un site: Jev choisit les pages utiles, le LLM rédige le rapport, contrôlé contre le texte lu."""

import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from urllib.parse import urldefrag, urlparse

from loguru import logger
from playwright.sync_api import Error as PlaywrightError

from . import events, jev, llm
from .browser import Browser
from .events import emit, span

MAX_PAGES = 8
MAX_PER_SECTION = 3
MAX_SIBLINGS = 4
REL_PROB = 0.25
MIN_PROB = 0.08
SNAP_CUTOFF = 0.75
SURE_SAME = 0.9
MAYBE_SAME = 0.65
MAX_LINKS = 40
MAX_CHARS_PAGE = 14000
NONE_OPTION = "aucun de ces liens"
DOMAIN = re.compile(r"(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s]*)?", re.I)
ANALYSE = re.compile(r"analys|audit|liste|résum|présent|décri|inspect", re.I)
DEFAULT_SECTIONS = [
    ("services", "Services proposés", "services offered"),
    ("tarifs", "Tarifs", "pricing and rates"),
    ("faq", "FAQ", "frequently asked questions"),
]
PLAN_SYSTEM = """The user wants information extracted from a website. Reply JSON only:
{"sections": [{"key": "short_id", "title": "title in the user's language", "hint": "what to look for, in English"}]}
1 to 5 sections, exactly what the user asked for."""
SECTION_SYSTEM = """You extract ONE section of a structured report about a website, using ONLY the page texts provided.
Reply JSON only: {"summary": "2 sentences in French describing the site",
 "items": [{"title": "...", "details": "..."}]}
Items for the requested section: each service, each offer/plan (put its price options inside details), each FAQ
question with its answer... Copy prices and figures exactly as written. Keep EVERY item found. If the site has
nothing for this section, return an empty items list. Never invent anything."""


@dataclass
class Section:
    key: str
    title: str
    hint: str


def site_url(request: str) -> str | None:
    m = DOMAIN.search(request)
    return f"https://{m.group(1)}{m.group(2) or ''}" if m and ANALYSE.search(request) else None


def plan_sections(request: str) -> list[Section]:
    if llm.available():
        try:
            raw = llm.chat_json(PLAN_SYSTEM, request).get("sections")
            secs = [Section(str(x["key"]), str(x["title"]), str(x["hint"])) for x in raw if isinstance(x, dict)]
            if secs:
                return secs[:5]
        except (llm.LlmError, KeyError, TypeError) as err:
            logger.warning("sections par défaut: {}", err)
    return [Section(*d) for d in DEFAULT_SECTIONS]


def internal_links(br: Browser, home: str) -> list[tuple[str, str]]:
    host = urlparse(home).netloc.removeprefix("www.")
    seen = {urldefrag(home)[0].rstrip("/")}
    out: list[tuple[str, str]] = []
    for text, href in br.links():
        url = urldefrag(href)[0].rstrip("/")
        if urlparse(url).netloc.removeprefix("www.") == host and url not in seen:
            seen.add(url)
            out.append((text or urlparse(url).path, url))
    return out[:MAX_LINKS]


def _parent(url: str) -> str:
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[0]


def _siblings(pick: str, links: list[tuple[str, str]]) -> list[str]:
    parent = _parent(pick)
    if not parent:
        return []
    return [u for _, u in links if u != pick and _parent(u) == parent][:MAX_SIBLINGS]


def pick_pages(sections: list[Section], links: list[tuple[str, str]]) -> list[str]:
    labels = [f"{i + 1}. {t} ({urlparse(u).path or '/'})" for i, (t, u) in enumerate(links)] + [NONE_OPTION]
    primary: list[str] = []
    for sec in sections:
        with span("choose", f"Trouver les pages « {sec.title} »") as sp:
            d = jev.choose("Site links:\n" + "\n".join(labels), f"Which link most likely leads to: {sec.hint}?", labels)
            ranked = sorted(d.probabilities.items(), key=lambda kv: -kv[1])
            floor = max(MIN_PROB, ranked[0][1] * REL_PROB)
            picks = []
            for label, p in ranked:
                if label == NONE_OPTION or p < floor or len(picks) >= MAX_PER_SECTION:
                    break
                picks.append(label)
            if not picks:
                sp["status"], sp["detail"] = "miss", "Jev ne voit aucun lien adapté"
                continue
            sp["detail"] = "Jev choisit : " + ", ".join(x.split("(", 1)[-1].rstrip(")") for x in picks)
            primary += [links[labels.index(x)][1] for x in picks]
    extra = [u for p in dict.fromkeys(primary) for u in _siblings(p, links)]
    return list(dict.fromkeys(primary + extra))


def read_pages(br: Browser, urls: list[str]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for i, url in enumerate(urls[:MAX_PAGES], 1):
        with span("page", f"Page n°{i} : {urlparse(url).path or '/'}", url=url) as pg:
            try:
                br.open(url)
            except (PlaywrightError, OSError) as err:
                logger.warning("page {} inaccessible: {}", url, err)
                pg["status"], pg["detail"] = "error", "Page inaccessible"
                continue
            texts[url] = br.text()[:MAX_CHARS_PAGE]
            pg["detail"] = f"{len(texts[url])} caractères lus"
    return texts


def _flat(text: str) -> str:
    return re.sub(r"[\s  ]+", "", text).lower()


def grounded(item: dict, flat: str) -> bool:
    text = f"{item.get('title', '')} {item.get('details', '')}"
    return all(_flat(n) in flat for n in re.findall(r"\d[\d\s .,]*\d|\d", text))


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9à-ÿ]+", " ", re.sub(r"\s*\([^)]*\)\s*$", "", title).lower()).strip()


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _same(a: str, b: str, ratio: float) -> bool:
    if ratio >= SURE_SAME:
        return True
    if ratio < MAYBE_SAME:
        return False
    return jev.yes_no(f"A: {a}\nB: {b}", "Do A and B ask the same question or describe the same thing?").label == "oui"


def dedupe(items: list[dict], lines: list[str]) -> tuple[list[dict], int]:
    out: list[dict] = []
    for it in items:
        title = re.sub(r"\s*\([^)]*\)\s*$", "", str(it.get("title", ""))).strip()
        title = (get_close_matches(title, lines, n=1, cutoff=SNAP_CUTOFF) or [title])[0]
        details = str(it.get("details", ""))
        best = max(out, key=lambda k: _ratio(k["title"], title), default=None)
        if best is None or not _same(best["title"], title, _ratio(best["title"], title)):
            out.append({"title": title, "details": details, "count": 1})
            continue
        best["count"] += 1
        if len(details) > len(best["details"]):
            best["details"] = details
    return out, len(items) - len(out)


def _ask_section(sec: Section, body: str) -> dict:
    user = f"Section: {sec.title} ({sec.hint})\n\n{body}"
    data = llm.chat_json(SECTION_SYSTEM, user, max_tokens=8000)
    if not data.get("items"):
        logger.warning("rubrique {} vide, nouvel essai", sec.key)
        again = llm.chat_json(SECTION_SYSTEM, user, max_tokens=8000)
        return again if again.get("items") else data
    return data


def write_report(sections: list[Section], texts: dict[str, str]) -> tuple[dict, int, int]:
    body = "\n".join(f"=== PAGE {u} ===\n{t}" for u, t in texts.items())
    with ThreadPoolExecutor(max_workers=len(sections)) as pool:
        ask = events.bind(_ask_section)
        answers = list(pool.map(lambda sec: ask(sec, body), sections))
    flat, dropped, merged, out = _flat(body), 0, 0, []
    lines = list(dict.fromkeys(ln.strip() for ln in body.split("\n") if 8 <= len(ln.strip()) <= 140))
    for sec, data in zip(sections, answers):
        items = [i for i in data.get("items", []) if isinstance(i, dict)]
        kept = [i for i in items if grounded(i, flat)]
        dropped += len(items) - len(kept)
        unique, n = dedupe(kept, lines)
        merged += n
        out.append({"key": sec.key, "title": sec.title, "items": unique})
    summary = next((str(d["summary"]) for d in answers if d.get("summary")), "")
    return {"summary": summary, "sections": out}, dropped, merged


def analyse_site(request: str, url: str, shared: Browser | None = None) -> bool:
    with span("plan", "Comprendre la demande (LLM)") as sp:
        sections = plan_sections(request)
        sp["detail"] = " · ".join(s.title for s in sections)
    with nullcontext(shared) if shared else Browser() as br:
        with span("page", "Page d'accueil", url=url) as pg:
            br.open(url)
            home = br.text()[:MAX_CHARS_PAGE]
            pg["detail"] = f"{len(home)} caractères lus"
            links = internal_links(br, url)
        texts = {url: home}
        with span("search", f"Repérer les pages utiles parmi {len(links)} liens du site") as sr:
            urls = pick_pages(sections, links) if links else []
            sr["detail"] = f"{len(urls)} page(s) à lire"
        texts.update(read_pages(br, urls))
    with span("extract", "Rédiger le rapport (LLM)") as sp:
        try:
            report, dropped, merged = write_report(sections, texts)
        except llm.LlmError as err:
            sp["status"], sp["detail"] = "error", f"LLM indisponible: {err}"
            return False
        n = sum(len(s["items"]) for s in report["sections"])
        sp["detail"] = (
            f"{n} éléments retenus"
            + (f", {dropped} retiré(s) car absents du texte du site" if dropped else "")
            + (f", {merged} doublon(s) fusionné(s)" if merged else "")
        )
    emit("report", report["summary"], sections=report["sections"], dropped=dropped, merged=merged, pages=list(texts))
    return True
