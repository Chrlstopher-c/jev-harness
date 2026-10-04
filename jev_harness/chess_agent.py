"""Joue une partie d'échecs: le LLM écrit le plan, Jev choisit parmi les coups annotés, les coups sont de vrais clics."""
import time

import chess
from loguru import logger

from . import jev, llm
from .actor import Actor
from .chess_adapters import BoardAdapter, Position
from .chess_view import Candidate, candidates, material, phase, state_text
from .events import span
from .session import Session

REPLAN_EVERY = 8
REPLAN_SWING = 3
WAIT_TURN_S = 90
MOVE_SETTLE_S = 4
TOP_SHOWN = 4
PLAN_SYSTEM = """You are a chess coach. Reply JSON only:
{"opening": "name of the opening or the idea", "plan": "one short sentence: the strategic plan for the next moves",
 "priorities": ["2 to 4 short priorities such as control the center, castle, attack the king"]}"""


class ChessAgent:
    def __init__(self, session: Session, adapter: BoardAdapter, safety: bool = True) -> None:
        self.s, self.adapter, self.safety = session, adapter, safety
        self.actor = Actor(session.br.page)
        self.plan, self.opening = "", ""
        self.plan_at, self.plan_balance = 0, 0
        self.evals: list[int] = []
        self.moves = 0

    def play(self) -> str:
        t0 = time.time()
        pos = self.adapter.read()
        self.s.say("assistant", f"Je joue les {'blancs' if pos.mine == 'w' else 'noirs'} sur le {self.adapter.name}.")
        while pos.status == "playing" and not self.s.stop_requested:
            if pos.turn == pos.mine:
                self._my_move(pos)
            elif not self._wait_turn(pos):
                return "L'adversaire ne joue plus, je m'arrête."
            pos = self.adapter.read()
        return self._summary(pos, time.time() - t0)

    def _wait_turn(self, pos: Position) -> bool:
        return self.s.wait_until(lambda: self.adapter.read().turn == pos.mine or self.adapter.read().status != "playing", WAIT_TURN_S)

    def _my_move(self, pos: Position) -> None:
        board = chess.Board(pos.fen)
        with span("move", f"Coup {board.fullmove_number}") as sp:
            self._maybe_replan(board, pos)
            cands = candidates(board, self.safety)
            pick, probs = self._choose(board, pos, cands)
            self._publish(board, pos, cands, probs, pick)
            self.s.say("assistant", f"Coup {board.fullmove_number} · {pick.san}" + (f" ({', '.join(pick.tags)})" if pick.tags else ""))
            self._execute(pick.move, board, pos)
            self.moves += 1
            if pos.eval_cp is not None:
                self.evals.append(pos.eval_cp)
            sp["detail"] = pick.san

    def _choose(self, board: chess.Board, pos: Position, cands: list[Candidate]) -> tuple[Candidate, dict[str, float]]:
        mate = next((c for c in cands if "CHECKMATE" in c.tags), None)
        if mate or len(cands) == 1:
            pick = mate or cands[0]
            return pick, {pick.label: 1.0}
        state = state_text(board, board.turn, self.plan, pos.last)
        labels = [c.label for c in cands]
        d = jev.choose(state, "Which move is best for the plan and the position?", labels)
        return cands[labels.index(d.label)], d.probabilities

    def _maybe_replan(self, board: chess.Board, pos: Position) -> None:
        balance = material(board) * (1 if board.turn == chess.WHITE else -1)
        due = not self.plan or board.fullmove_number - self.plan_at >= REPLAN_EVERY or abs(balance - self.plan_balance) >= REPLAN_SWING
        if not due or not llm.available():
            return
        with span("plan", "Mettre à jour le plan (LLM)") as sp:
            user = (f"I play {'white' if board.turn == chess.WHITE else 'black'}. FEN: {pos.fen}. Phase: {phase(board)}. "
                    f"Material balance for me: {balance}. Last opponent move: {pos.last or 'none'}.")
            try:
                data = llm.chat_json(PLAN_SYSTEM, user)
                self.plan, self.opening = str(data.get("plan", ""))[:200], str(data.get("opening", ""))[:80]
                sp["detail"] = f"{self.opening} — {self.plan}"
            except llm.LlmError as err:
                sp["status"], sp["detail"] = "partial", f"plan inchangé ({err})"
        self.plan_at, self.plan_balance = board.fullmove_number, balance

    def _click_square(self, square: str) -> None:
        xy = self.adapter.square_xy(square)
        if xy is None:
            raise RuntimeError(f"case {square} introuvable")
        self.actor.click(*xy)

    def _execute(self, move: chess.Move, board: chess.Board, pos: Position) -> None:
        for attempt in range(2):
            self._click_square(chess.square_name(move.from_square))
            self._click_square(chess.square_name(move.to_square))
            if move.promotion:
                self.s.pump(250)
                xy = self.adapter.promotion_xy(chess.piece_symbol(move.promotion))
                if xy:
                    self.actor.click(*xy)
            if self.s.wait_until(lambda: self.adapter.read().fen != pos.fen, MOVE_SETTLE_S):
                return
            logger.warning("coup {} non pris en compte (essai {})", move.uci(), attempt + 1)
        raise RuntimeError(f"le coup {board.san(move)} n'a pas été joué sur le plateau")

    def _publish(self, board: chess.Board, pos: Position, cands: list[Candidate], probs: dict[str, float], pick: Candidate) -> None:
        top = sorted(cands, key=lambda c: -probs.get(c.label, 0))[:TOP_SHOWN]
        self.s.hub.broadcast({"t": "chess", "opening": self.opening, "plan": self.plan, "move_no": board.fullmove_number,
                              "phase": phase(board), "eval": pos.eval_cp, "pick": pick.san, "safety": self.safety,
                              "candidates": [{"san": c.san, "tags": c.tags, "p": round(probs.get(c.label, 0), 3)} for c in top]})

    def _summary(self, pos: Position, seconds: float) -> str:
        if self.s.stop_requested:
            return "Partie interrompue."
        board = chess.Board(pos.fen)
        if pos.status == "checkmate":
            won = board.turn != (chess.WHITE if pos.mine == "w" else chess.BLACK)
            result = "J'ai gagné par échec et mat." if won else "J'ai perdu par échec et mat."
        else:
            result = "Partie nulle."
        trend = f" Évaluation finale : {self.evals[-1] / 100:+.1f}." if self.evals else ""
        return f"{result} {self.moves} coups en {round(seconds)} s.{trend}"
