"""Génère bench/data/tasks.json (graine fixe): python -m bench.make_tasks (STOCKFISH_JS requis pour les échecs)."""

import sys

from loguru import logger

from .chess_tasks import make_chess_tasks
from .common import TASKS_FILE, save_tasks
from .text_tasks import make_text_tasks
from .vision_tasks import make_desktop_tasks, make_synthetic_tasks

SEED = 20261005
TEXT_COUNTS = {"lecture_en": 60, "lecture_fr": 40, "comparaison": 50, "calcul": 50, "deux_sauts": 50, "oui_non": 90}


def main() -> int:
    tasks = make_text_tasks(SEED, TEXT_COUNTS) + make_synthetic_tasks(SEED, 15) + make_desktop_tasks()
    try:
        tasks += make_chess_tasks(SEED, 80)
    except (OSError, ValueError) as err:
        logger.error("tâches d'échecs ignorées: {}", err)
    save_tasks(tasks)
    cats: dict[str, int] = {}
    for t in tasks:
        cats[t.category] = cats.get(t.category, 0) + 1
    print(f"{len(tasks)} tâches -> {TASKS_FILE}\n" + "\n".join(f"  {k}: {v}" for k, v in sorted(cats.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
