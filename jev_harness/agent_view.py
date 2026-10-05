"""Contexte réduit pour Jev: tâche, étape courante, historique court; options d'action numérotées."""

import re
from dataclasses import dataclass

from .observe import Element, Observation

TOP_ELEMENTS = 16
STATE_CHARS = 700
HELP = "ask the user for help"
INPUT_WORDS = re.compile(r"cherch|recherch|saisi|écri|entr|tape|rempl|champ|search|type|fill|enter", re.I)


@dataclass
class Action:
    kind: str
    element: Element | None = None

    def describe(self) -> str:
        names = {
            "click": "clic sur",
            "type": "saisie dans",
            "toggle": "case à cocher",
            "select": "choix dans la liste",
            "scroll_down": "défilement vers le bas",
            "scroll_up": "défilement vers le haut",
            "enter": "touche Entrée",
            "back": "page précédente",
            "help": "demande d'aide",
        }
        return names[self.kind] + (f" « {self.element.label} »" if self.element else "")


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2}


def rank_elements(obs: Observation, focus: str, kind: str = "other") -> list[Element]:
    terms = _terms(focus)
    wants_input = kind in ("type", "password") or bool(INPUT_WORDS.search(focus))

    def score(e: Element) -> float:
        hits = sum(t in e.label.lower() for t in terms)
        empty_field = e.kind in ("text", "password") and not e.value
        kind_bonus = (1.5 if wants_input and empty_field else 0) + (
            1.0 if kind in ("toggle", "select") and e.kind == kind else 0
        )
        return hits + kind_bonus + (0.5 if e.focused else 0) - e.y / 100000

    usable = [e for e in obs.items if not e.disabled]
    return sorted(usable, key=lambda e: -score(e))[:TOP_ELEMENTS]


def _element_options(elements: list[Element]) -> dict[str, Action]:
    out: dict[str, Action] = {}
    for e in elements:
        if e.kind in ("text", "password"):
            if not e.value:
                out[f"type in #{e.id} {e.label}"] = Action("type", e)
        elif e.kind == "toggle":
            out[f"toggle #{e.id} {e.label}"] = Action("toggle", e)
        elif e.kind == "select":
            out[f"choose in #{e.id} {e.name or 'list'}"] = Action("select", e)
        else:
            out[f"click #{e.id} {e.label}"] = Action("click", e)
    return out


def build(
    obs: Observation,
    task: str,
    subgoal: str,
    idx: int,
    total: int,
    history: list[str],
    typed_last: bool,
    kind: str = "other",
) -> tuple[str, list[str], dict[str, Action]]:
    options = _element_options(rank_elements(obs, f"{subgoal} {task}", kind))
    if obs.can_down:
        options["scroll down"] = Action("scroll_down")
    if obs.can_up:
        options["scroll up"] = Action("scroll_up")
    if typed_last:
        options["press Enter"] = Action("enter")
    options["go back"] = Action("back")
    options[HELP] = Action("help")
    where = f"scrolled {round(100 * obs.scroll_y / obs.scroll_max)}%" if obs.scroll_max else "page fits the screen"
    state = (
        f"Task: {task}\nStep {idx + 1}/{total}: {subgoal}\nLast actions: {'; '.join(history[-3:]) or 'none'}\n"
        f"Page: {obs.title[:60]} ({where})"
    )[:STATE_CHARS]
    return state, list(options), options
