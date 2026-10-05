"""Observation d'une page: éléments interactifs visibles, numérotés, pour qu'un agent choisisse où agir."""

from dataclasses import dataclass

from loguru import logger
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from .events import timed
from .scripts import load_js

MAX_ITEMS = 60
SCRIPT = load_js("observe")


@dataclass
class Element:
    id: int
    tag: str
    type: str
    role: str
    name: str
    value: str
    checked: bool
    disabled: bool
    focused: bool
    x: int
    y: int
    w: int
    h: int
    options: list[str]
    sel_index: int
    frame: int = 0

    @property
    def kind(self) -> str:
        if self.tag == "textarea" or (
            self.tag == "input" and self.type in ("", "text", "search", "email", "url", "tel", "number", "password")
        ):
            return "password" if self.type == "password" else "text"
        if self.tag == "input" and self.type in ("checkbox", "radio") or self.role in ("checkbox", "radio"):
            return "toggle"
        if self.tag == "select":
            return "select"
        return "click"

    @property
    def label(self) -> str:
        return self.name or self.value or f"{self.tag} sans nom"


@dataclass
class Observation:
    items: list[Element]
    title: str
    url: str
    scroll_y: int
    scroll_max: int

    @property
    def signature(self) -> str:
        return f"{self.url}|{self.scroll_y}|" + ";".join(f"{e.name}:{e.value}" for e in self.items[:25])

    @property
    def can_down(self) -> bool:
        return self.scroll_y < self.scroll_max - 4

    @property
    def can_up(self) -> bool:
        return self.scroll_y > 4


FRAME_LIMIT = 6
MIN_FRAME_W, MIN_FRAME_H = 80, 40
FIELDS = (
    "tag",
    "type",
    "role",
    "name",
    "value",
    "checked",
    "disabled",
    "focused",
    "x",
    "y",
    "w",
    "h",
    "options",
    "selIndex",
)


def _frame_items(page: Page, raw_main: dict) -> list[dict]:
    """Éléments de la page puis des cadres intégrés visibles, en coordonnées de la page principale."""
    out = [{**it, "frame": 0} for it in raw_main["items"]]
    vw, vh = raw_main["w"], raw_main["h"]
    for idx, fr in enumerate(page.frames[1:], start=1):
        if idx > FRAME_LIMIT:
            break
        try:
            box = fr.frame_element().bounding_box()
            if (
                not box
                or box["width"] < MIN_FRAME_W
                or box["height"] < MIN_FRAME_H
                or box["y"] > vh
                or box["y"] + box["height"] < 0
            ):
                continue
            for it in fr.evaluate(SCRIPT, MAX_ITEMS)["items"]:
                x, y = it["x"] + round(box["x"]), it["y"] + round(box["y"])
                if 0 <= x < vw and 0 <= y < vh:
                    out.append({**it, "x": x, "y": y, "frame": idx})
        except PlaywrightError as err:
            logger.debug("frame {} ignorée: {}", idx, err)
            continue
    return out


def observe(page: Page) -> Observation:
    with timed("browser", "observer la page"):
        raw = page.evaluate(SCRIPT, MAX_ITEMS)
        items = _frame_items(page, raw)
    elements = [
        Element(
            i + 1,
            tag=it["tag"],
            type=it["type"],
            role=it["role"],
            name=it["name"],
            value=it["value"],
            checked=it["checked"],
            disabled=it["disabled"],
            focused=it["focused"],
            x=it["x"],
            y=it["y"],
            w=it["w"],
            h=it["h"],
            options=it["options"],
            sel_index=it["selIndex"],
            frame=it["frame"],
        )
        for i, it in enumerate(items)
    ]
    return Observation(elements, raw["title"], raw["url"], raw["scrollY"], raw["scrollMax"])
