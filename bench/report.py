"""Rapport comparatif JevK5 vs decider-2b-vision (Markdown): python -m bench.report."""

import statistics as st
import sys

from loguru import logger

from .common import RESULTS_DIR, Task, load_results, load_tasks
from .metrics import BLUNDER_CP, bootstrap_ci, choice_stats, chosen_cost, paired_accuracy

MODELS = ("jevk5", "decider-2b-vision")
MEASURED_VRAM = {"jevk5": "8 154 Mo (nvidia-smi sur jevk5-serve, 05/10)"}


def _rows(name: str) -> dict[str, dict]:
    data = load_results(name)
    return {r["id"]: r for r in data["rows"] if "probs" in r}


def _by_category(tasks: list[Task]) -> dict[str, list[Task]]:
    out: dict[str, list[Task]] = {}
    for t in tasks:
        out.setdefault(t.category, []).append(t)
    return out


def _fmt_acc(stats) -> str:  # noqa: ANN001
    return f"{stats.accuracy:5.1%} [{stats.ci[0]:5.1%} ; {stats.ci[1]:5.1%}]"


def gold_section(cat: str, tasks: list[Task], res: dict[str, dict[str, dict]]) -> list[str]:
    line = [f"| {cat} |"]
    common = [t for t in tasks if all(t.id in res[m] for m in res)]
    for m in MODELS:
        if m not in res or not any(t.id in res[m] for t in tasks):
            line.append(" n/a |")
            continue
        sub = [t for t in tasks if t.id in res[m]]
        s = choice_stats([t.gold for t in sub], [res[m][t.id]["probs"] for t in sub])
        line.append(f" {_fmt_acc(s)} · n={s.n} · ECE {s.ece:.2f} |")
    if len(res) == 2 and common:
        pa = paired_accuracy(
            [t.gold for t in common],
            [res[MODELS[0]][t.id]["probs"] for t in common],
            [res[MODELS[1]][t.id]["probs"] for t in common],
        )
        ci = f"[{pa['ci'][0]:+.1%} ; {pa['ci'][1]:+.1%}]"
        line.append(f" {pa['diff']:+.1%} {ci} · p={pa['p']:.3f} ({pa['only_a']}/{pa['only_b']}) |")
    else:
        line.append(" — |")
    return ["".join(line)]


def alt_yesno_section(tasks: list[Task], res: dict[str, dict[str, dict]]) -> list[str]:
    try:
        alt = _rows("jevk5-yesno-choice")
    except (OSError, ValueError):
        return []
    swapped = {**res, "jevk5": alt}
    return [
        line.replace("| oui_non_ancre |", "| oui_non_ancre (Jev posé en choix yes/no) |")
        for line in gold_section("oui_non_ancre", tasks, swapped)
    ]


def chess_section(tasks: list[Task], res: dict[str, dict[str, dict]]) -> list[str]:
    out = [
        "",
        "### Échecs (perte en centipions vs meilleur coup Stockfish, plus bas = meilleur)",
        "",
        "| Choix | Perte moyenne [IC95] | Gaffes ≥200 cp | Meilleur coup |",
        "|---|---|---|---|",
    ]
    baselines = {
        "heuristique (1er candidat)": [t.costs[0] for t in tasks],
        "hasard (moyenne)": [st.mean(t.costs) for t in tasks],
    }
    for m in MODELS:
        if m in res and all(t.id in res[m] for t in tasks):
            baselines[m] = [chosen_cost(t, res[m][t.id]["probs"]) for t in tasks]
    for name, vals in baselines.items():
        lo, hi = bootstrap_ci(vals)
        blunders = sum(v >= BLUNDER_CP for v in vals) / len(vals)
        best = sum(v == 0 for v in vals) / len(vals)
        out.append(f"| {name} | {st.mean(vals):.0f} [{lo:.0f} ; {hi:.0f}] | {blunders:.0%} | {best:.0%} |")
    both = [t for t in tasks if all(t.id in res.get(m, {}) for m in MODELS)]
    if len(both) == len(tasks):
        diffs = [
            chosen_cost(t, res[MODELS[0]][t.id]["probs"]) - chosen_cost(t, res[MODELS[1]][t.id]["probs"]) for t in tasks
        ]
        lo, hi = bootstrap_ci(diffs)
        out += [
            "",
            f"Écart apparié de perte (JevK5 − decider) : {st.mean(diffs):+.0f} cp [{lo:+.0f} ; {hi:+.0f}] "
            "(négatif = JevK5 meilleur).",
        ]
    return out


def latency_section(res: dict[str, dict[str, dict]]) -> list[str]:
    out = [
        "",
        "### Latence et mémoire",
        "",
        "| Modèle | p50 (ms/requête) | p95 (ms) | VRAM crête |",
        "|---|---|---|---|",
    ]
    for m in res:
        meta = load_results(m)["meta"]
        out.append(
            f"| {m} | {meta.get('latency_p50_ms', 0):.0f} | {meta.get('latency_p95_ms', 0):.0f} | "
            f"{meta.get('vram_peak_mb', MEASURED_VRAM.get(m, '?'))} |"
        )
    return out


def build() -> str:
    tasks = load_tasks()
    res = {}
    for m in MODELS:
        try:
            res[m] = _rows(m)
        except (OSError, ValueError):
            logger.warning("pas de résultats pour {}", m)
    lines = [
        "# JevK5 vs decider-2b-vision",
        "",
        "Exactitude top-1 (IC95 de Wilson), moyenne des deux ordres d'options. Écart = JevK5 − decider "
        "avec IC95 bootstrap, p exact de McNemar (paires discordantes JevK5 seul / decider seul).",
        "",
        "| Catégorie | JevK5 | decider-2b-vision | Écart apparié |",
        "|---|---|---|---|",
    ]
    for cat, ts in sorted(_by_category([t for t in tasks if t.gold is not None]).items()):
        lines += gold_section(cat, ts, res)
        if cat == "oui_non_ancre":
            lines += alt_yesno_section(ts, res)
    chess = [t for t in tasks if t.costs]
    if chess:
        lines += chess_section(chess, res)
    return "\n".join(lines + latency_section(res)) + "\n"


def main() -> int:
    text = build()
    (RESULTS_DIR / "REPORT.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
