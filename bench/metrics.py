"""Métriques du banc: exactitude + IC de Wilson, calibration, pertes d'échecs, comparaisons appariées."""

import math
import random
import statistics as st
from dataclasses import dataclass

from .common import Task

BOOTSTRAP = 4000
BLUNDER_CP = 200
EPS = 1e-6


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_p(only_a: int, only_b: int) -> float:
    """p bilatéral exact (binomiale 0,5) sur les paires discordantes."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def ece(confidences: list[float], correct: list[bool], bins: int = 10) -> float:
    total = len(confidences)
    out = 0.0
    for b in range(bins):
        idx = [i for i, c in enumerate(confidences) if b / bins <= c < (b + 1) / bins or (b == bins - 1 and c == 1.0)]
        if idx:
            gap = abs(sum(correct[i] for i in idx) / len(idx) - sum(confidences[i] for i in idx) / len(idx))
            out += len(idx) / total * gap
    return out


@dataclass
class CategoryStats:
    n: int
    accuracy: float
    ci: tuple[float, float]
    logloss: float
    brier: float
    ece: float


def choice_stats(golds: list[int], probs: list[list[float]]) -> CategoryStats:
    correct = [max(range(len(p)), key=p.__getitem__) == g for g, p in zip(golds, probs)]
    conf = [max(p) / (sum(p) or 1.0) for p in probs]
    logloss = st.mean(-math.log(max(EPS, p[g] / (sum(p) or 1.0))) for g, p in zip(golds, probs))
    brier = st.mean(sum(((i == g) - x / (sum(p) or 1.0)) ** 2 for i, x in enumerate(p)) for g, p in zip(golds, probs))
    k = sum(correct)
    return CategoryStats(len(golds), k / len(golds), wilson(k, len(golds)), logloss, brier, ece(conf, correct))


def bootstrap_ci(values: list[float], seed: int = 1) -> tuple[float, float]:
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP))
    return means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP) - 1]


def chosen_cost(task: Task, probs: list[float]) -> float:
    assert task.costs is not None
    return task.costs[max(range(len(probs)), key=probs.__getitem__)]


def paired_accuracy(golds: list[int], probs_a: list[list[float]], probs_b: list[list[float]]) -> dict:
    ok_a = [max(range(len(p)), key=p.__getitem__) == g for g, p in zip(golds, probs_a)]
    ok_b = [max(range(len(p)), key=p.__getitem__) == g for g, p in zip(golds, probs_b)]
    diffs = [float(a) - float(b) for a, b in zip(ok_a, ok_b)]
    only_a = sum(a and not b for a, b in zip(ok_a, ok_b))
    only_b = sum(b and not a for a, b in zip(ok_a, ok_b))
    return {
        "diff": st.mean(diffs),
        "ci": bootstrap_ci(diffs),
        "p": mcnemar_p(only_a, only_b),
        "only_a": only_a,
        "only_b": only_b,
    }
