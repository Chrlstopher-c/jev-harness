"""Plateau d'échecs: un adaptateur par site pour lire la position, trouver les cases, promouvoir."""

from dataclasses import dataclass
from typing import Protocol

from loguru import logger
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from .events import timed
from .scripts import load_js

READ_LOCAL = load_js("board-read")
RECT = load_js("rect")


@dataclass
class Position:
    fen: str
    turn: str
    mine: str
    status: str
    last: str
    eval_cp: int | None


class BoardAdapter(Protocol):
    name: str

    def read(self) -> Position: ...
    def square_xy(self, square: str) -> tuple[int, int, int, int] | None: ...
    def promotion_xy(self, piece: str) -> tuple[int, int, int, int] | None: ...


def _eval_cp(raw: str, mine: str) -> int | None:
    """Évaluation affichée par la page (points de vue des blancs) convertie du point de vue du joueur."""
    sign = 1 if mine == "w" else -1
    if raw.startswith("mate"):
        return sign * (10000 if int(raw.split()[1]) > 0 else -10000)
    return sign * int(raw) if raw.lstrip("-").isdigit() else None


class LocalBoard:
    """Plateau local du banc d'essai (page /chess/): l'état est publié dans les attributs data- de #board."""

    name = "plateau local"

    def __init__(self, page: Page) -> None:
        self.page = page

    @staticmethod
    def matches(page: Page) -> bool:
        try:
            return bool(page.evaluate("!!document.querySelector('#board[data-fen]')"))
        except PlaywrightError as err:
            logger.debug("détection du plateau impossible: {}", err)
            return False

    def read(self) -> Position:
        with timed("browser", "lire le plateau"):
            d = self.page.evaluate(READ_LOCAL)
        return Position(d["fen"], d["turn"], d["mine"], d["status"], d["last"], _eval_cp(d["eval"], d["mine"]))

    def square_xy(self, square: str) -> tuple[int, int, int, int] | None:
        r = self.page.evaluate(RECT, f'[data-square="{square}"]')
        return (r["x"], r["y"], r["w"], r["h"]) if r else None

    def promotion_xy(self, piece: str) -> tuple[int, int, int, int] | None:
        r = self.page.evaluate(RECT, f'#promo:not([hidden]) [data-promo="{piece}"]')
        return (r["x"], r["y"], r["w"], r["h"]) if r else None


def detect(page: Page) -> BoardAdapter | None:
    """Adaptateur adapté à la page courante, ou None. Pour un autre site, ajouter ici son adaptateur."""
    return LocalBoard(page) if LocalBoard.matches(page) else None
