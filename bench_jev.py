"""Banc de latence de Jev: taille du contexte, concurrence, questions groupées. Usage: python bench_jev.py"""
import statistics as st
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

URL = "http://127.0.0.1:8090/v1/systemone"
CHARS = [600, 1200, 2400, 4800, 9600, 19200]
REPS = 5
Q_YN = {"type": "noul", "instructions": "Does the text state the height of the tower?"}
Q_CH = {"type": "choice", "instructions": "Which option is the best answer?",
        "criteria": [f"option {i} about the tower" for i in range(1, 9)]}


def corpus() -> str:
    r = httpx.get("https://fr.wikipedia.org/w/api.php", timeout=20, headers={"User-Agent": "jev-bench/0.1"},
                  params={"action": "query", "prop": "extracts", "explaintext": 1, "titles": "Tour Eiffel", "format": "json"})
    return next(iter(r.json()["query"]["pages"].values()))["extract"]


def call(state: str, questions: dict) -> tuple[float, float, int]:
    t = time.perf_counter()
    r = httpx.post(URL, json={"state": state, "questions": questions}, timeout=120).json()
    return r["latency_ms"], (time.perf_counter() - t) * 1000, r["usage"]["input_tokens"]


def row(label: str, runs: list[tuple[float, float, int]]) -> None:
    print(f"{label:34} tokens {runs[0][2]:5d} | serveur {st.mean(r[0] for r in runs):6.0f} ms | "
          f"aller-retour {st.mean(r[1] for r in runs):6.0f} ms")


if __name__ == "__main__":
    text = corpus()
    call(text[:600], {"q": Q_YN})
    print("== 1. latence selon le contexte (séquentiel, moyenne de", REPS, "appels)")
    for n in CHARS:
        row(f"oui/non  {n:6d} car.", [call(text[:n], {"q": Q_YN}) for _ in range(REPS)])
        row(f"choix 8  {n:6d} car.", [call(text[:n], {"q": Q_CH}) for _ in range(REPS)])
    print("== 2. concurrence (contexte 1200 car., oui/non): temps du lot entier")
    for k in (1, 2, 4, 8):
        t = time.perf_counter()
        with ThreadPoolExecutor(k) as ex:
            runs = list(ex.map(lambda _: call(text[:1200], {"q": Q_YN}), range(k)))
        wall = (time.perf_counter() - t) * 1000
        print(f"{k} appels simultanés | lot {wall:6.0f} ms | par appel serveur {st.mean(r[0] for r in runs):5.0f} ms"
              f" | vs séquentiel {k * 1000 // 1:d}x?".replace(f" | vs séquentiel {k * 1000}x?", ""))
    print("== 3. questions groupées sur un même contexte (1200 car.)")
    for k in (1, 2, 4):
        qs = {f"q{i}": {**Q_YN, "instructions": f"Does the text mention topic number {i}?"} for i in range(k)}
        row(f"{k} question(s) dans 1 appel", [call(text[:1200], qs) for _ in range(REPS)])
