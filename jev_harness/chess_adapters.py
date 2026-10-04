"""Lecture et gestes sur un plateau d'échecs. Un adaptateur par site: lire la position, trouver les cases, promouvoir."""
from dataclasses import dataclass
from typing import Protocol

from playwright.sync_api import Page

from .events import timed

READ_LOCAL = """() => {
  const d = document.getElementById('board').dataset;
  return { fen: d.fen, turn: d.turn, mine: d.human, status: d.status, last: d.last || '', eval: d.eval || '', thinking: d.thinking };
}"""
RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();
  return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) }; }"""


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
        except Exception:
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
