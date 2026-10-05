"""Exécute le banc sur decider-2b-vision (venv de doom-agent, GPU): python -m bench.run_decider."""

import sys
import time
from types import ModuleType

from loguru import logger
from PIL import Image

from .common import BENCH_DIR, Task, load_tasks
from .render import render
from .runner_common import Ask, run

MODEL_ID = "Mapika/decider-2b-vision"


def load_image(task: Task) -> Image.Image | None:
    if task.image is None:
        return None
    if task.image.startswith("synth:"):
        return render(task.image[len("synth:") :])
    try:
        return Image.open(BENCH_DIR / "data" / task.image).convert("RGB")
    except OSError as err:
        logger.error("image illisible ({}): {}", task.image, err)
        raise


def make_ask(model_id: str) -> tuple[Ask, ModuleType]:
    import torch
    from decider.infer import Example, Q
    from decider.vision.model import VisionDecisionModel

    model = VisionDecisionModel(model_id, grad_ckpt=False).cuda().eval()

    def ask(task: Task, order: list[int]) -> tuple[list[float], float]:
        options = [task.options[i] for i in order]
        example = Example(task.state, [Q(task.question, options, 0)])
        image = load_image(task)
        with torch.inference_mode():
            inp = model.prepare([(image, example)])
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            probs = torch.softmax(model.slot_logits(inp), -1)[0, : len(options)].float().cpu().tolist()
            torch.cuda.synchronize()
        return probs, (time.perf_counter() - t0) * 1000

    return ask, torch


def main() -> int:
    tasks = load_tasks()
    try:
        ask, torch = make_ask(MODEL_ID)
        run(
            tasks,
            ask,
            "decider-2b-vision",
            {"model": MODEL_ID, "tasks": "toutes"},
            extra=lambda: {"vram_peak_mb": round(torch.cuda.max_memory_allocated() / 2**20)},
        )
    except (OSError, RuntimeError, ImportError) as err:
        logger.error("banc decider interrompu: {}", err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
