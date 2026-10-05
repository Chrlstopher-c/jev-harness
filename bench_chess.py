"""Banc d'échecs: coups de Jev vs heuristique vs hasard, jugés par Stockfish (perte en centipions)."""

import os
import random
import shutil
import statistics as st
import sys

import chess
import chess.engine
from loguru import logger

from jev_harness import jev
from jev_harness.chess_view import Candidate, candidates, state_text

POSITIONS = int(os.environ.get("BENCH_POSITIONS", 60))
DEPTH = int(os.environ.get("BENCH_DEPTH", 10))
MODE = os.environ.get("BENCH_MODE", "engine")
BLUNDER_CP = 200
CP_CAP = 800
BOOTSTRAP = 2000
SEED = 7
QUESTION = "Which move is best for the plan and the position?"


def engine_command() -> list[str]:
    script = os.environ.get("STOCKFISH_JS", "")
    if script:
        return ["node", script]
    binary = shutil.which("stockfish")
    if binary is None:
        raise SystemExit("Stockfish introuvable: définir STOCKFISH_JS (script wasm) ou installer stockfish")
    return [binary]


def realistic_positions(engine: chess.engine.SimpleEngine, count: int, rng: random.Random) -> list[chess.Board]:
    """Parties de Stockfish (profondeur 4, un des 3 meilleurs coups au hasard): positions plausibles."""
    out: list[chess.Board] = []
    while len(out) < count:
        board = chess.Board()
        for _ in range(rng.randint(8, 50)):
            if board.is_game_over():
                break
            infos = engine.analyse(board, chess.engine.Limit(depth=4), multipv=3)
            board.push(rng.choice([i["pv"][0] for i in infos]))
        if not board.is_game_over() and len(list(board.legal_moves)) > 3:
            out.append(board)
    return out


def random_positions(count: int, rng: random.Random) -> list[chess.Board]:
    out: list[chess.Board] = []
    while len(out) < count:
        board = chess.Board()
        for _ in range(rng.randint(6, 40)):
            if board.is_game_over():
                break
            board.push(rng.choice(list(board.legal_moves)))
        if not board.is_game_over() and len(list(board.legal_moves)) > 3:
            out.append(board)
    return out


def score_moves(
    engine: chess.engine.SimpleEngine, board: chess.Board, moves: list[chess.Move]
) -> dict[chess.Move, int]:
    infos = engine.analyse(board, chess.engine.Limit(depth=DEPTH), multipv=len(moves), root_moves=moves)
    out: dict[chess.Move, int] = {}
    for info in infos:
        move = info["pv"][0]
        out[move] = max(-CP_CAP, min(CP_CAP, info["score"].pov(board.turn).score(mate_score=CP_CAP)))
    return out


def jev_pick(board: chess.Board, cands: list[Candidate]) -> Candidate:
    labels = [c.label for c in cands]
    decision = jev.choose(state_text(board, board.turn, "", ""), QUESTION, labels)
    return cands[labels.index(decision.label)]


def evaluate(engine: chess.engine.SimpleEngine, board: chess.Board, rng: random.Random) -> dict[str, float] | None:
    cands = candidates(board, True)
    if len(cands) < 2:
        return None
    all_moves = list(board.legal_moves)
    try:
        scores = score_moves(engine, board, all_moves)
        picks = {"jev": jev_pick(board, cands).move, "heuristique": cands[0].move, "hasard": rng.choice(cands).move}
    except (chess.engine.EngineError, OSError, ValueError) as err:
        logger.error("position ignorée ({}): {}", board.fen(), err)
        return None
    best = max(scores.values())
    best_cand = max(scores.get(c.move, -CP_CAP) for c in cands)
    result = {name: float(best - scores.get(move, -CP_CAP)) for name, move in picks.items()}
    result["couverture"] = float(best - best_cand)
    return result


def bootstrap_ci(values: list[float], rng: random.Random) -> tuple[float, float]:
    means = sorted(st.mean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP))
    return means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP)]


def report(rows: list[dict[str, float]], rng: random.Random) -> None:
    print(f"\n{len(rows)} positions ({MODE}), Stockfish profondeur {DEPTH}, perte en centipions (plus bas = meilleur)")
    for name in ("jev", "heuristique", "hasard"):
        vals = [r[name] for r in rows]
        lo, hi = bootstrap_ci(vals, rng)
        blunders = sum(v >= BLUNDER_CP for v in vals) / len(vals)
        top = sum(v == 0 for v in vals) / len(vals)
        print(
            f"{name:12} perte moyenne {st.mean(vals):6.1f} [IC95 {lo:6.1f} ; {hi:6.1f}] médiane {st.median(vals):5.1f} "
            f"| gaffes ≥{BLUNDER_CP}: {blunders:5.1%} | meilleur coup: {top:5.1%}"
        )
    cover = [r["couverture"] for r in rows]
    print(
        f"Couverture des candidats: le meilleur coup absolu manque dans {sum(c > 0 for c in cover) / len(cover):.1%} "
        f"des cas (perte moyenne évitable {st.mean(cover):.1f})"
    )


def main() -> int:
    rng = random.Random(SEED)
    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_command())
    except (OSError, chess.engine.EngineError) as err:
        logger.error("moteur impossible à lancer: {}", err)
        return 1
    rows: list[dict[str, float]] = []
    try:
        boards = random_positions(POSITIONS, rng) if MODE == "random" else realistic_positions(engine, POSITIONS, rng)
        for i, board in enumerate(boards, 1):
            row = evaluate(engine, board, rng)
            if row:
                rows.append(row)
            print(f"\r{i}/{POSITIONS}", end="", file=sys.stderr, flush=True)
    finally:
        engine.quit()
    if not rows:
        logger.error("aucune position évaluée")
        return 1
    report(rows, rng)
    return 0


if __name__ == "__main__":
    sys.exit(main())
