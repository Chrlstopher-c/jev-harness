"""Gestes réels dans le navigateur: curseur visible, clic, frappe, défilement, surbrillance de la cible."""

import math
import random

from loguru import logger
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from .events import timed
from .scripts import load_js

GHOST = load_js("ghost")
MARK = load_js("mark")
MOVE_STEPS = 14


class Actor:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.pos = (640.0, 360.0)

    def _ghost(self, x: float, y: float) -> None:
        try:
            self.page.evaluate(GHOST, [x, y])
        except PlaywrightError as err:
            logger.debug("curseur fantôme non affiché: {}", err)

    def move_to(self, x: float, y: float) -> None:
        x0, y0 = self.pos
        bend = random.uniform(-40, 40)
        for i in range(1, MOVE_STEPS + 1):
            t = i / MOVE_STEPS
            e = t * t * (3 - 2 * t)
            px = x0 + (x - x0) * e + math.sin(math.pi * t) * bend * 0.3
            py = y0 + (y - y0) * e + math.sin(math.pi * t) * bend
            self.page.mouse.move(px, py)
            self._ghost(px, py)
            self.page.wait_for_timeout(random.randint(5, 14))
        self.pos = (x, y)

    def mark(self, x: int, y: int, w: int, h: int) -> None:
        try:
            self.page.evaluate(MARK, [x, y, min(w, 600), min(h, 300)])
        except PlaywrightError as err:
            logger.debug("surbrillance non affichée: {}", err)

    def click(self, x: int, y: int, w: int = 20, h: int = 20) -> None:
        with timed("browser", "déplacer la souris et cliquer"):
            self.mark(x, y, w, h)
            self.move_to(x, y)
            self.page.mouse.down()
            self.page.wait_for_timeout(random.randint(40, 90))
            self.page.mouse.up()

    def type_text(self, text: str) -> None:
        with timed("browser", "saisir du texte"):
            self.page.keyboard.type(text, delay=random.randint(35, 75))

    def press(self, key: str) -> None:
        with timed("browser", f"touche {key}"):
            self.page.keyboard.press(key)

    def scroll(self, dy: int) -> None:
        with timed("browser", "défiler"):
            self.move_to(self.pos[0], self.pos[1])
            for _ in range(3):
                self.page.mouse.wheel(0, dy / 3)
                self.page.wait_for_timeout(60)
