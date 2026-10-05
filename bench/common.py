"""Format commun des tâches et des résultats du banc (JSON sur disque)."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from loguru import logger

BENCH_DIR = Path(__file__).parent
TASKS_FILE = BENCH_DIR / "data" / "tasks.json"
RESULTS_DIR = BENCH_DIR / "results"


@dataclass
class Task:
    id: str
    category: str
    kind: str  # "choice" | "yesno"
    state: str
    question: str
    options: list[str]
    gold: int | None = None
    image: str | None = None  # chemin relatif à bench/data, ou "synth:<json>" rendu par le runner
    costs: list[float] | None = None  # perte (centipions) par option, pour les échecs
    meta: dict = field(default_factory=dict)


def save_tasks(tasks: list[Task], path: Path = TASKS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps([asdict(t) for t in tasks], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as err:
        logger.error("tâches non sauvegardées ({}): {}", path, err)
        raise


def load_tasks(path: Path = TASKS_FILE) -> list[Task]:
    try:
        return [Task(**row) for row in json.loads(path.read_text(encoding="utf-8"))]
    except (OSError, ValueError) as err:
        logger.error("tâches illisibles ({}): {}", path, err)
        raise


def save_results(name: str, rows: list[dict], meta: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    try:
        path.write_text(json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    except OSError as err:
        logger.error("résultats non sauvegardés ({}): {}", path, err)
        raise
    return path


def load_results(name: str) -> dict:
    try:
        return json.loads((RESULTS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        logger.error("résultats illisibles ({}): {}", name, err)
        raise
