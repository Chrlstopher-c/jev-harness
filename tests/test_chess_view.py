import chess

from jev_harness.chess_adapters import _eval_cp
from jev_harness.chess_view import candidates, material, phase


def test_mate_in_one_is_first() -> None:
    board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    assert "CHECKMATE" in candidates(board, True)[0].tags


def test_safety_filters_blunders() -> None:
    board = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    assert all(c.net > -2 for c in candidates(board, True))


def test_material_and_phase() -> None:
    board = chess.Board()
    assert material(board) == 0 and phase(board) == "opening"


def test_eval_sign_follows_player() -> None:
    assert _eval_cp("120", "w") == 120 and _eval_cp("120", "b") == -120
    assert _eval_cp("mate 3", "b") == -10000
