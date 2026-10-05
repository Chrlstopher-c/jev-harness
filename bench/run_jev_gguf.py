"""JevK5 Q8_0 via llama-server (venv de doom-agent, paquet jevk5): python -m bench.run_jev_gguf [url]."""

import subprocess
import sys

from loguru import logger

from .common import Task, load_tasks
from .runner_common import Ask, run

TEMPERATURE, KNOCKOUT = 1.22, 0.93  # valeurs du fichier jevk5-4b-v0.3-Q8_0.gguf (fiche JevK5-GGUF)


def gpu_used_mb() -> dict:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
        return {"gpu_used_mb_total": int(out.split()[0])}
    except (OSError, subprocess.SubprocessError, ValueError) as err:
        logger.warning("nvidia-smi indisponible: {}", err)
        return {}


def make_ask(url: str) -> Ask:
    from jevk5 import JevK5GGUF

    model = JevK5GGUF(url=url, temperature=TEMPERATURE, knockout_temperature=KNOCKOUT)

    def ask(task: Task, order: list[int]) -> tuple[list[float], float]:
        options = [task.options[i] for i in order]
        probs, _ = model.probabilities(
            task.state, {"type": "choice", "instructions": task.question, "criteria": options}
        )
        return [float(probs[o]) for o in options], model.last_seconds * 1000

    return ask


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8098"
    tasks = [t for t in load_tasks() if t.image is None]
    try:
        run(
            tasks,
            make_ask(url),
            "jevk5-q8",
            {"model": "JevK5 v0.3 Q8_0 (GGUF, llama-server)", "yesno": "posé en choix"},
            extra=gpu_used_mb,
        )
    except (OSError, ImportError) as err:
        logger.error("banc Jev Q8 interrompu: {}", err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
