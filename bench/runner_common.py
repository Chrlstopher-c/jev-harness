"""Boucle commune: chaque tâche est posée dans deux ordres d'options (biais de position), probabilités moyennées."""

import statistics as st
import time
from collections.abc import Callable
from datetime import datetime, timezone

from loguru import logger

from .common import Task, save_results

# ask(task, ordre des options) -> (probabilités dans cet ordre, latence ms)
Ask = Callable[[Task, list[int]], tuple[list[float], float]]


def orders_for(task: Task, both: bool) -> list[list[int]]:
    n = len(task.options)
    forward = list(range(n))
    return [forward, forward[::-1]] if both and n > 1 else [forward]


def ask_all_orders(task: Task, ask: Ask, both: bool) -> tuple[list[float], list[float]]:
    sums = [0.0] * len(task.options)
    latencies: list[float] = []
    orders = orders_for(task, both)
    for order in orders:
        probs, ms = ask(task, order)
        latencies.append(ms)
        for position, option_index in enumerate(order):
            sums[option_index] += probs[position] / len(orders)
    return sums, latencies


def run(
    tasks: list[Task],
    ask: Ask,
    name: str,
    meta: dict,
    both_orders: bool = True,
    extra: Callable[[], dict] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    t0 = time.time()
    for i, task in enumerate(tasks, 1):
        try:
            probs, latencies = ask_all_orders(task, ask, both_orders)
        except Exception as err:  # noqa: BLE001 - un échec isolé ne doit pas arrêter le banc, il est consigné
            logger.error("tâche {} en échec: {}", task.id, err)
            rows.append({"id": task.id, "error": str(err)})
            continue
        rows.append({"id": task.id, "probs": probs, "latency_ms": latencies})
        if i % 25 == 0:
            logger.info("{}: {}/{} ({} s)", name, i, len(tasks), round(time.time() - t0))
    lat = [x for r in rows for x in r.get("latency_ms", [])]
    meta = {
        **meta,
        **(extra() if extra else {}),
        "date": datetime.now(timezone.utc).isoformat(),
        "n_tasks": len(tasks),
        "errors": sum("error" in r for r in rows),
        "latency_p50_ms": st.median(lat) if lat else None,
        "latency_p95_ms": sorted(lat)[int(0.95 * len(lat))] if lat else None,
    }
    path = save_results(name, rows, meta)
    logger.info("résultats -> {}", path)
    return rows
