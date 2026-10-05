"""Vue d'une partie pour Jev: coups légaux annotés (python-chess), contexte court, garde-fou matériel optionnel."""

from dataclasses import dataclass

import chess

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
CENTER = {chess.D4, chess.E4, chess.D5, chess.E5}
MAX_CANDIDATES = 14
BLUNDER_NET = -2


@dataclass
class Candidate:
    move: chess.Move
    san: str
    tags: list[str]
    net: int
    score: float

    @property
    def label(self) -> str:
        return f"{self.san} ({', '.join(self.tags)})" if self.tags else self.san


def _captured_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return 1
    target = board.piece_at(move.to_square)
    return VALUES[target.piece_type] if target else 0


def risk_after(board: chess.Board, move: chess.Move) -> int:
    """Matériel que l'adversaire peut gagner en une réponse (échange simple, recapture comptée)."""
    mover = board.turn
    after = board.copy()
    after.push(move)
    worst = 0
    for reply in after.legal_moves:
        if not after.is_capture(reply):
            continue
        gain = _captured_value(after, reply)
        attacker = after.piece_at(reply.from_square)
        recapture = chess.Board(after.fen())
        recapture.push(reply)
        lost = VALUES[attacker.piece_type] if attacker and recapture.is_attacked_by(mover, reply.to_square) else 0
        worst = max(worst, gain - lost)
    return worst


def _tags(board: chess.Board, move: chess.Move, gain: int, risk: int) -> list[str]:
    piece = board.piece_at(move.from_square)
    after = board.copy()
    after.push(move)
    tags: list[str] = []
    if after.is_checkmate():
        tags.append("CHECKMATE")
    elif board.gives_check(move):
        tags.append("check")
    if gain:
        tags.append(
            f"captures {NAMES[board.piece_at(move.to_square).piece_type] if board.piece_at(move.to_square) else 'pawn'}"
        )
    if move.promotion:
        tags.append("promotes")
    if board.is_castling(move):
        tags.append("castles")
    back = 0 if board.turn == chess.WHITE else 7
    if (
        piece
        and piece.piece_type in (chess.KNIGHT, chess.BISHOP)
        and chess.square_rank(move.from_square) == back
        and board.fullmove_number <= 14
    ):
        tags.append("develops")
    if move.to_square in CENTER and piece and piece.piece_type in (chess.PAWN, chess.KNIGHT):
        tags.append("center")
    if risk >= 1:
        tags.append(f"loses {risk}" if gain < risk else f"trade {gain}-{risk}")
    return tags


def candidates(board: chess.Board, safety: bool) -> list[Candidate]:
    out: list[Candidate] = []
    for move in board.legal_moves:
        gain, risk = _captured_value(board, move), 0
        risk = risk_after(board, move)
        tags = _tags(board, move, gain, risk)
        net = gain - risk + (1000 if "CHECKMATE" in tags else 0)
        score = (
            net * 10
            + (2 if "check" in tags else 0)
            + (3 if "castles" in tags else 0)
            + (2 if "develops" in tags else 0)
            + (1.5 if "center" in tags else 0)
            + (8 if move.promotion else 0)
        )
        out.append(Candidate(move, board.san(move), tags, net, score))
    if safety:
        safe = [c for c in out if c.net > BLUNDER_NET]
        out = safe or out
    return sorted(out, key=lambda c: -c.score)[:MAX_CANDIDATES]


def material(board: chess.Board) -> int:
    """Balance du matériel du point de vue des blancs (positif = avantage blanc)."""
    return sum(VALUES[p.piece_type] * (1 if p.color else -1) for p in board.piece_map().values())


def phase(board: chess.Board) -> str:
    pieces = len(board.piece_map())
    return "opening" if board.fullmove_number <= 10 and pieces >= 28 else "endgame" if pieces <= 12 else "middlegame"


def state_text(board: chess.Board, me: chess.Color, plan: str, last: str) -> str:
    bal = material(board) * (1 if me else -1)
    mat = "equal material" if bal == 0 else f"{'up' if bal > 0 else 'down'} {abs(bal)} pawns of material"
    return (
        f"You play {'white' if me else 'black'}. Move {board.fullmove_number}, {phase(board)}, {mat}.\n{board}\n"
        f"Last opponent move: {last or 'none'}\n"
        f"Plan: {plan or 'develop pieces, control the center, keep the king safe'}"
    )
