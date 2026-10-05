import pytest

from bench.common import Task
from bench.metrics import choice_stats, chosen_cost, ece, mcnemar_p, paired_accuracy, wilson
from bench.render import render
from bench.runner_common import ask_all_orders
from bench.text_tasks import make_text_tasks
from bench.vision_tasks import make_synthetic_tasks


def test_wilson_bounds() -> None:
    lo, hi = wilson(8, 10)
    assert 0.44 < lo < 0.5 < 0.8 < hi < 0.97
    assert wilson(0, 0) == (0.0, 0.0)


def test_mcnemar_exact() -> None:
    assert mcnemar_p(0, 0) == 1.0
    assert mcnemar_p(10, 0) == pytest.approx(2 / 1024)
    assert mcnemar_p(5, 5) == 1.0


def test_ece_perfect_and_overconfident() -> None:
    assert ece([1.0, 1.0], [True, True]) == 0.0
    assert ece([0.9] * 10, [True] * 5 + [False] * 5) == pytest.approx(0.4)


def test_choice_stats_accuracy_and_calibration() -> None:
    stats = choice_stats([0, 1, 2], [[0.7, 0.2, 0.1], [0.1, 0.8, 0.1], [0.5, 0.4, 0.1]])
    assert stats.n == 3 and stats.accuracy == pytest.approx(2 / 3)
    assert 0.0 <= stats.ece <= 1.0 and stats.logloss > 0


def test_paired_accuracy_counts_discordant_pairs() -> None:
    a = [[1.0, 0.0]] * 4
    b = [[0.0, 1.0], [0.0, 1.0], [1.0, 0.0], [1.0, 0.0]]
    out = paired_accuracy([0, 0, 0, 0], a, b)
    assert out["only_a"] == 2 and out["only_b"] == 0 and out["diff"] == pytest.approx(0.5)


def test_chosen_cost_follows_argmax() -> None:
    task = Task("c", "echecs", "choice", "s", "q", ["a", "b", "c"], None, costs=[0.0, 50.0, 300.0])
    assert chosen_cost(task, [0.1, 0.2, 0.7]) == 300.0


def test_text_tasks_are_deterministic_and_consistent() -> None:
    counts = {"lecture_en": 5, "lecture_fr": 5, "comparaison": 5, "calcul": 5, "deux_sauts": 5, "oui_non": 10}
    first, second = make_text_tasks(11, counts), make_text_tasks(11, counts)
    assert [t.state for t in first] == [t.state for t in second]
    for t in first:
        assert t.gold is not None and 0 <= t.gold < len(t.options) and len(set(t.options)) == len(t.options)


def test_sum_and_lookup_gold_is_really_in_state() -> None:
    for t in make_text_tasks(5, {"lecture_en": 20, "calcul": 20}):
        if t.category == "lecture_en":
            assert t.options[t.gold] in t.state
        else:
            assert t.options[t.gold].endswith("euros")


def test_orders_average_back_to_original_option_order() -> None:
    task = Task("t", "x", "choice", "s", "q", ["a", "b", "c"], 0)

    def ask(_t: Task, order: list[int]) -> tuple[list[float], float]:
        favoured = [1.0 if i == 0 else 0.0 for i in order]  # le modèle préfère toujours l'option "a"
        return favoured, 1.0

    probs, lat = ask_all_orders(task, ask, both=True)
    assert probs == [1.0, 0.0, 0.0] and len(lat) == 2


def test_synthetic_images_render() -> None:
    tasks = make_synthetic_tasks(3, 2)
    assert len(tasks) == 8
    for t in tasks:
        assert t.image and render(t.image[len("synth:") :]).size == (448, 336)
