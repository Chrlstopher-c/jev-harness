"""Rendu déterministe des images synthétiques du banc de vision (spec JSON -> image PIL)."""

import json
import random

from PIL import Image, ImageDraw, ImageFont

SIZE = (448, 336)
COLORS = {"red": (220, 40, 40), "green": (40, 170, 70), "blue": (50, 90, 220), "yellow": (235, 200, 40)}
QUADRANTS = ["top-left", "top-right", "bottom-left", "bottom-right"]


def render(spec_json: str) -> Image.Image:
    spec = json.loads(spec_json)
    img = Image.new("RGB", SIZE, (245, 245, 245))
    draw = ImageDraw.Draw(img)
    rng = random.Random(spec["seed"])
    {"count": _count, "word": _word, "color": _color, "position": _position}[spec["type"]](draw, spec, rng)
    return img


def _spots(rng: random.Random, n: int, margin: int = 40, gap: int = 62) -> list[tuple[int, int]]:
    spots: list[tuple[int, int]] = []
    while len(spots) < n:
        p = (rng.randint(margin, SIZE[0] - margin), rng.randint(margin, SIZE[1] - margin))
        if all(abs(p[0] - q[0]) > gap or abs(p[1] - q[1]) > gap for q in spots):
            spots.append(p)
    return spots


def _count(draw: ImageDraw.ImageDraw, spec: dict, rng: random.Random) -> None:
    spots = _spots(rng, spec["n"] + spec["distractors"])
    for i, (x, y) in enumerate(spots):
        if i < spec["n"]:
            draw.rectangle([x - 22, y - 22, x + 22, y + 22], fill=COLORS["red"])
        else:
            draw.ellipse([x - 22, y - 22, x + 22, y + 22], fill=COLORS["blue"])


def _word(draw: ImageDraw.ImageDraw, spec: dict, rng: random.Random) -> None:
    font = ImageFont.load_default(size=72)
    draw.text((SIZE[0] // 2, SIZE[1] // 2), spec["word"], fill=(20, 20, 20), font=font, anchor="mm")


def _color(draw: ImageDraw.ImageDraw, spec: dict, rng: random.Random) -> None:
    draw.ellipse([124, 68, 324, 268], fill=COLORS[spec["color"]])


def _position(draw: ImageDraw.ImageDraw, spec: dict, rng: random.Random) -> None:
    right, bottom = "right" in spec["where"], "bottom" in spec["where"]
    x = rng.randint(SIZE[0] // 2 + 40, SIZE[0] - 40) if right else rng.randint(40, SIZE[0] // 2 - 40)
    y = rng.randint(SIZE[1] // 2 + 40, SIZE[1] - 40) if bottom else rng.randint(40, SIZE[1] // 2 - 40)
    draw.line([SIZE[0] // 2, 0, SIZE[0] // 2, SIZE[1]], fill=(180, 180, 180), width=2)
    draw.line([0, SIZE[1] // 2, SIZE[0], SIZE[1] // 2], fill=(180, 180, 180), width=2)
    draw.ellipse([x - 14, y - 14, x + 14, y + 14], fill=COLORS["red"])
