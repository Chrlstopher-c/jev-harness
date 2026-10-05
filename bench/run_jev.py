"""Exécute le banc sur JevK5 (serveur /v1/systemone du labo): python -m bench.run_jev."""

import sys

from loguru import logger

from jev_harness import jev

from .common import Task, load_tasks
from .runner_common import run


def ask_jev(task: Task, order: list[int], yesno_as_choice: bool = False) -> tuple[list[float], float]:
    options = [task.options[i] for i in order]
    if task.kind == "yesno" and not yesno_as_choice:
        reply, _ = jev._ask(task.state, {"type": "noul", "instructions": task.question})
        p_yes = float(reply["answers"]["q"]["noul"])
        return [p_yes, 1 - p_yes], float(reply["latency_ms"])
    reply, _ = jev._ask(task.state, {"type": "choice", "instructions": task.question, "criteria": options})
    probs = reply["answers"]["q"]["probabilities"]
    return [float(probs[o]) for o in options], float(reply["latency_ms"])


def main() -> int:
    """Sans argument: tout le texte (oui/non en `noul`). Avec --yesno-choice: oui/non seulement, posés en choix."""
    as_choice = "--yesno-choice" in sys.argv
    tasks = [t for t in load_tasks() if t.image is None and (t.kind == "yesno" or not as_choice)]
    name = "jevk5-yesno-choice" if as_choice else "jevk5"
    try:
        run(
            tasks,
            lambda t, o: ask_jev(t, o, as_choice),
            name,
            {"model": "JevK5", "runtime": "jevk5-serve /v1/systemone"},
        )
    except OSError as err:
        logger.error("banc Jev interrompu: {}", err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
