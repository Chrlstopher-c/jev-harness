"""Tâches d'échecs: choix parmi les coups candidats, pertes en centipions mesurées par Stockfish."""

import random

import chess
import chess.engine
from loguru import logger

from bench_chess import QUESTION, engine_command, realistic_positions, score_moves
from jev_harness.chess_view import candidates, state_text

from .common import Task


def make_chess_tasks(seed: int, count: int) -> list[Task]:
    rng = random.Random(seed)
    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_command())
    except (OSError, chess.engine.EngineError) as err:
        logger.error("moteur impossible à lancer: {}", err)
        raise
    tasks: list[Task] = []
    try:
        for i, board in enumerate(realistic_positions(engine, count, rng)):
            cands = candidates(board, True)
            if len(cands) < 2:
                continue
            scores = score_moves(engine, board, list(board.legal_moves))
            best = max(scores.values())
            costs = [float(best - scores.get(c.move, -800)) for c in cands]
            tasks.append(
                Task(
                    f"chess_{i}",
                    "echecs",
                    "choice",
                    state_text(board, board.turn, "", ""),
                    QUESTION,
                    [c.label for c in cands],
                    None,
                    costs=costs,
                    meta={"fen": board.fen()},
                )
            )
    finally:
        engine.quit()
    return tasks
