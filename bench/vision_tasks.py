"""Tâches de vision (decider-2b-vision seulement): images synthétiques et captures réelles du bureau virtuel."""

import json
import random

from .common import BENCH_DIR, Task
from .render import COLORS, QUADRANTS

INTRO = "This is a visual question about the image."
WORDS = ["apple", "tiger", "river", "cloud", "metal", "piano", "green", "stone", "light", "bread", "chair", "ocean"]
SHOTS_DIR = BENCH_DIR / "data" / "shots"


def _synth(spec: dict) -> str:
    return "synth:" + json.dumps(spec, sort_keys=True)


def _count_task(rng: random.Random, i: int) -> Task:
    n = rng.randint(1, 5)
    spec = {"type": "count", "n": n, "distractors": rng.randint(0, 3), "seed": rng.randrange(10**6)}
    return Task(
        f"vis_count_{i}",
        "vision_comptage",
        "choice",
        INTRO,
        "How many red squares are in the image?",
        ["1", "2", "3", "4", "5"],
        n - 1,
        image=_synth(spec),
    )


def _word_task(rng: random.Random, i: int) -> Task:
    words = rng.sample(WORDS, 4)
    word = rng.choice(words)
    spec = {"type": "word", "word": word, "seed": rng.randrange(10**6)}
    return Task(
        f"vis_word_{i}",
        "vision_lecture_mot",
        "choice",
        INTRO,
        "Which word is written in the image?",
        words,
        words.index(word),
        image=_synth(spec),
    )


def _color_task(rng: random.Random, i: int) -> Task:
    colors = list(COLORS)
    color = rng.choice(colors)
    return Task(
        f"vis_color_{i}",
        "vision_couleur",
        "choice",
        INTRO,
        "What color is the circle?",
        colors,
        colors.index(color),
        image=_synth({"type": "color", "color": color, "seed": 0}),
    )


def _position_task(rng: random.Random, i: int) -> Task:
    where = rng.choice(QUADRANTS)
    spec = {"type": "position", "where": where, "seed": rng.randrange(10**6)}
    return Task(
        f"vis_pos_{i}",
        "vision_position",
        "choice",
        INTRO,
        "In which quadrant is the red dot?",
        QUADRANTS,
        QUADRANTS.index(where),
        image=_synth(spec),
    )


def make_synthetic_tasks(seed: int, per_type: int) -> list[Task]:
    rng = random.Random(seed)
    makers = (_count_task, _word_task, _color_task, _position_task)
    return [make(rng, i) for i in range(per_type) for make in makers]


def make_desktop_tasks() -> list[Task]:
    """Captures réelles du bureau virtuel (bench/data/shots/<n>_<k>.jpg = n fenêtres de terminal ouvertes)."""
    out: list[Task] = []
    for path in sorted(SHOTS_DIR.glob("*.jpg")):
        n = int(path.stem.split("_")[0])
        out.append(
            Task(
                f"vis_desktop_{path.stem}",
                "vision_bureau",
                "choice",
                INTRO,
                "How many terminal windows are open?",
                ["1", "2", "3", "4"],
                n - 1,
                image=f"shots/{path.name}",
            )
        )
    return out
