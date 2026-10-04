"""Agent d'interaction: le LLM planifie, Jev choisit chaque élément, les gestes sont réels, l'avancement est vérifié sur la page."""
import re
import unicodedata
from dataclasses import dataclass

from loguru import logger

from . import jev, llm
from .actor import Actor
from .agent_view import Action, build
from .events import span, timed
from .observe import Element, Observation, observe
from .session import Session

MAX_STEPS = 30
MAX_PLAN = 8
STUCK_LIMIT = 3
NO_OPTION = "none of these options"
REPEAT_LIMIT = 4
CHECK_SYSTEM = """You judge whether a browser task is accomplished. Reply JSON only: {"accomplished": true or false}.
Base it ONLY on the page title, URL and visible labels given. Say true only when the page clearly shows the task result."""
SETTLE_MS = 700
ASK_TIMEOUT_S = 180
KINDS = {"type", "toggle", "click", "press", "password", "select", "other"}
SEARCH_FIELD = re.compile(r"search|recherch|cherch", re.I)
RISKY = re.compile(r"payer|paiement|commander|acheter|confirmer|envoyer|publier|supprimer|souscrire|abonner|s'inscrire|valider|"
                   r"\b(buy|pay|order|submit|send|post|purchase|checkout|subscribe|delete|remove)\b", re.I)

PLAN_SYSTEM = """You plan a browser task for the user, who wrote in French. Reply JSON only:
{"steps": [{"text": "short French sentence", "kind": "type|toggle|click|press|password|select|other",
 "target": "visible label of the field or button (empty if unknown)", "value": "text to type, or the option to choose"}]}
kind: type = write text in a field; select = choose an option in a dropdown list (value = the option); password = a password field (the user types it himself); toggle = tick a checkbox;
click = click a button or link; press = press Enter; other = anything else. At most 8 steps, in order.
Values come ONLY from the user's words. Never invent data. The browser is ALREADY on the right page: no "open the page" step."""


@dataclass
class Step:
    text: str
    kind: str = "other"
    target: str = ""
    value: str = ""
    done: bool = False

    def describe(self) -> str:
        t = f"“{self.target}”" if self.target else "the right element"
        by_kind = {"type": f"type “{self.value}” in the field {t}", "password": f"let the user type the password in {t}",
                   "toggle": f"tick the box {t}", "click": f"click {t}" if self.target else "click the most relevant result or button",
                   "press": "press Enter", "select": f"choose “{self.value}” in the list {t}"}
        return by_kind.get(self.kind) or self.text or "continue the task"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode())


def _matches(label: str, target: str) -> bool:
    nl, nt = _norm(label), _norm(target)
    words = [_norm(w) for w in re.findall(r"\w+", target) if len(w) > 3]
    return bool(nt) and (nt in nl or nl in nt or any(w and w in nl for w in words))


class Agent:
    def __init__(self, session: Session, task: str) -> None:
        self.s, self.task = session, task
        self.actor = Actor(session.br.page)
        self.steps: list[Step] = [Step(task)]
        self.history: list[str] = []
        self.typed_last = False
        self.recent: list[str] = []
        self.stuck = 0
        self.last_sig = ""

    @property
    def current(self) -> Step | None:
        return next((st for st in self.steps if not st.done), None)

    def run(self) -> str:
        self._plan()
        for n in range(1, MAX_STEPS + 1):
            if self.s.stop_requested:
                return "Arrêté."
            finished, msg = self._step(n)
            if finished:
                return msg
        return self._give_up(observe(self.s.br.page), f"Limite de {MAX_STEPS} étapes atteinte, je m'arrête.")[1]

    def _plan(self) -> None:
        obs = observe(self.s.br.page)
        names = "; ".join(e.label for e in obs.items[:14])
        with span("plan", "Planifier la tâche (LLM)") as sp:
            try:
                data = llm.chat_json(PLAN_SYSTEM, f"Task: {self.task}\nPage: {obs.title} {obs.url}\nVisible: {names}")
                steps = [Step(str(x.get("text", "")), x.get("kind") if x.get("kind") in KINDS else "other",
                              str(x.get("target") or ""), str(x.get("value") or "")) for x in data.get("steps", []) if isinstance(x, dict)]
                self.steps = steps[:MAX_PLAN] or self.steps
            except llm.LlmError as err:
                sp["status"], sp["detail"] = "partial", f"plan simple (LLM indisponible: {err})"
            sp.setdefault("detail", f"{len(self.steps)} étapes")
        self.s.say("assistant", "Plan : " + " → ".join(st.describe() for st in self.steps))

    def _step(self, n: int) -> tuple[bool, str]:
        with span("act", f"Étape {n}") as sp:
            obs = observe(self.s.br.page)
            if self._stuck(obs):
                return self._give_up(obs, "Je tourne en rond sans que la page change : je m'arrête, dis-moi comment continuer.")
            cur = self.current
            state, labels, actions = build(obs, self.task, cur.describe() if cur else self.task,
                                           self.steps.index(cur) if cur else 0, len(self.steps), self.history,
                                           self.typed_last, cur.kind if cur else "other")
            action, label = self._pick(cur, obs, state, labels, actions)
            if self._repeats(label) >= REPEAT_LIMIT:
                return self._give_up(obs, "Je répète la même action sans progrès : dis-moi comment continuer.")
            sp["detail"] = action.describe()
            self.s.say("assistant", f"Étape {n} · {action.describe()}")
            finished, msg = self._do(action)
            if not finished:
                self._verify(observe(self.s.br.page))
                if self.current is None:
                    return True, "Tâche terminée."
            return finished, msg

    def _candidates(self, cur: Step | None, obs: Observation) -> list[Element]:
        if cur is None or not cur.target:
            return []
        kinds = {"type": ("text",), "toggle": ("toggle",), "click": ("click",), "password": ("password",), "select": ("select",)}.get(cur.kind, ())
        return [e for e in obs.items if e.kind in kinds and not e.disabled and _matches(e.label, cur.target)
                and not (cur.kind == "type" and e.value)]

    def _pick(self, cur: Step | None, obs: Observation, state: str, labels: list[str], actions: dict[str, Action]) -> tuple[Action, str]:
        """Un seul élément correspond à la cible: on agit directement. Plusieurs ou aucun: Jev tranche."""
        cand = self._candidates(cur, obs)
        if cur and cur.kind == "press" and (self.typed_last or any(e.focused for e in obs.items)):
            return Action("enter"), "press Enter"
        if len(cand) == 1:
            label = next(k for k, a in actions.items() if a.element is cand[0])
            return actions[label], label
        if len(cand) > 1:
            labels = [k for k in labels if actions[k].element is None or actions[k].element in cand]
        label = jev.choose(state, "What is the best next action to make progress on the current step?", labels).label
        return actions[label], label

    def _give_up(self, obs: Observation, msg: str) -> tuple[bool, str]:
        """Avant d'abandonner, un seul appel LLM vérifie si la tâche est en fait accomplie."""
        user = f"Task: {self.task}\nTitle: {obs.title}\nURL: {obs.url}\nLabels: {'; '.join(e.label for e in obs.items[:14])}"
        try:
            if llm.chat_json(CHECK_SYSTEM, user).get("accomplished") is True:
                return True, "Tâche terminée."
        except llm.LlmError:
            pass
        return True, msg

    def _repeats(self, label: str) -> int:
        self.recent.append(label)
        del self.recent[:-10]
        return self.recent.count(label)

    def _verify(self, obs: Observation) -> None:
        fields = [e for e in obs.items if e.kind == "text" and e.value]
        for st in self.steps:
            if st.done:
                continue
            if st.kind == "type":
                st.done = any(_norm(st.value) in _norm(e.value) for e in fields)
            elif st.kind == "toggle":
                st.done = any(e.kind == "toggle" and e.checked and (not st.target or _matches(e.label, st.target)) for e in obs.items)
            elif st.kind == "select":
                st.done = any(e.kind == "select" and _norm(st.value) and _norm(st.value) in _norm(e.value) for e in obs.items)

    def _mark(self, kind: str, label: str = "") -> None:
        pending = [st for st in self.steps if st.kind == kind and not st.done]
        hit = next((st for st in pending if label and _matches(label, st.target)), None)
        cur = self.current
        hit = hit or (cur if cur and cur.kind == kind else None)
        if hit:
            hit.done = True

    def _stuck(self, obs: Observation) -> bool:
        self.stuck = self.stuck + 1 if obs.signature == self.last_sig else 0
        self.last_sig = obs.signature
        return self.stuck >= STUCK_LIMIT

    def _do(self, a: Action) -> tuple[bool, str]:
        self.history.append(a.describe())
        if a.kind == "help":
            return True, "J'ai besoin d'aide : précise ce que je dois faire ensuite."
        try:
            return self._act(a)
        except Exception as err:
            logger.exception("geste en échec")
            return False, f"geste en échec: {err}"

    def _act(self, a: Action) -> tuple[bool, str]:
        e, page = a.element, self.s.br.page
        if a.kind in ("click", "toggle") and e:
            if self._needs_confirm(e) and not self.s.confirm(f"Cliquer sur « {e.label} » ?"):
                return True, f"Action « {e.label} » refusée, je m'arrête."
            self.actor.click(e.x, e.y, e.w, e.h)
            if a.kind == "click":
                self._mark("click", e.label)
        elif a.kind == "type" and e:
            return self._type(e)
        elif a.kind == "select" and e:
            return self._select(e)
        elif a.kind in ("scroll_down", "scroll_up"):
            self.actor.scroll(int(page.viewport_size["height"] * 0.7) * (1 if a.kind == "scroll_down" else -1) if page.viewport_size else 500)
        elif a.kind == "enter":
            if self._enter_is_sensitive() and not self.s.confirm("Appuyer sur Entrée dans ce champ (cela peut envoyer le formulaire) ?"):
                return True, "Envoi refusé, je m'arrête."
            self.actor.press("Enter")
            self._mark("press")
        elif a.kind == "back":
            page.go_back(wait_until="commit")
        self.typed_last = False
        self.s.pump(SETTLE_MS)
        return False, ""

    def _enter_is_sensitive(self) -> bool:
        focus = next((e for e in observe(self.s.br.page).items if e.focused), None)
        return not (focus and (focus.type == "search" or SEARCH_FIELD.search(focus.label)))

    def _needs_confirm(self, e: Element) -> bool:
        return bool(RISKY.search(e.label)) or e.type == "submit"

    def _type(self, e: Element) -> tuple[bool, str]:
        self.actor.click(e.x, e.y, e.w, e.h)
        if e.kind == "password":
            return self._handoff(e)
        value = self._value_for(e)
        if value is None:
            value = self.s.ask(f"Que dois-je saisir dans « {e.label} » ?", ASK_TIMEOUT_S)
            if value is None:
                return True, "Pas de réponse, je m'arrête."
        self.actor.type_text(value)
        self.typed_last = True
        self.s.pump(300)
        return False, ""

    def _select(self, e: Element) -> tuple[bool, str]:
        self.actor.mark(e.x, e.y, e.w, e.h)
        self.actor.move_to(e.x, e.y)
        option = self._option_for(e)
        if option is None:
            option = self.s.ask(f"Quelle option choisir dans « {e.name or 'la liste'} » ?", ASK_TIMEOUT_S)
            option = next((o for o in e.options if _norm(option or "") and _norm(option or "") in _norm(o)), None)
            if option is None:
                return True, "Option introuvable, je m'arrête."
        with timed("browser", "choisir une option"):
            self.s.br.page.frames[e.frame].locator("select").nth(e.sel_index).select_option(label=option)
        self.s.pump(300)
        return False, ""

    def _option_for(self, e: Element) -> str | None:
        """L'option voulue figure dans l'étape: correspondance directe. Sinon Jev choisit parmi les options."""
        pending = [st for st in self.steps if st.kind == "select" and not st.done and st.value]
        want = next((st.value for st in pending if _matches(e.name, st.target)), pending[0].value if len(pending) == 1 else "")
        exact = next((o for o in e.options if want and (_norm(want) == _norm(o) or _norm(want) in _norm(o))), None)
        if exact or not e.options:
            return exact
        d = jev.choose(f"Field: {e.name}\nWanted: {want or self.task[:160]}", "Which option matches what the user wants?", e.options[:20] + [NO_OPTION])
        return None if d.label == NO_OPTION else d.label

    def _value_for(self, e: Element) -> str | None:
        pending = [st for st in self.steps if st.kind == "type" and not st.done and st.value]
        hit = next((st for st in pending if _matches(e.label, st.target)), None) or (pending[0] if len(pending) == 1 else None)
        return hit.value if hit else None

    def _handoff(self, e: Element) -> tuple[bool, str]:
        self.s.say("assistant", f"Saisis toi-même le mot de passe dans « {e.label} » (je ne le tape jamais), puis écris « ok ».")
        reply = self.s.ask("", ASK_TIMEOUT_S, handoff=True)
        if reply is None:
            return True, "Pas de réponse, je m'arrête."
        self._mark("password", e.label)
        return False, ""
