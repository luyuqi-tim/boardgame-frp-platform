"""Fully playable Tic-Tac-Toe demo game plugin."""

from __future__ import annotations

from typing import Any

from boardgame_platform.game_api import (
    GameOverInfo,
    GamePlugin,
    MoveResult,
    PlayerInfo,
    register_game,
)


@register_game
class TicTacToe(GamePlugin):
    game_id = "tictactoe"
    display_name = "井字棋 (Tic-Tac-Toe)"
    min_players = 2
    max_players = 2
    description = "经典 3×3 井字棋。X 先手，轮流落子，三连获胜。"

    WIN_LINES = (
        (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),
        (0, 3, 6),
        (1, 4, 7),
        (2, 5, 8),
        (0, 4, 8),
        (2, 4, 6),
    )

    def setup(self) -> None:
        if len(self.players) != 2:
            raise ValueError("Tic-Tac-Toe requires exactly 2 players")
        # Seat 0 = X (first), seat 1 = O
        self.board: list[str | None] = [None] * 9
        self.symbols: dict[str, str] = {
            self.players[0].player_id: "X",
            self.players[1].player_id: "O",
        }
        self.current: str = self.players[0].player_id
        self.winner: str | None = None
        self.draw: bool = False
        self.move_count: int = 0

    def validate(self, player_id: str, move: dict[str, Any]) -> MoveResult:
        if self.winner or self.draw:
            return MoveResult(ok=False, error="游戏已结束")
        if player_id not in self.symbols:
            return MoveResult(ok=False, error="你不是本局玩家")
        if player_id != self.current:
            return MoveResult(ok=False, error="还没轮到你")
        try:
            cell = int(move.get("cell"))
        except (TypeError, ValueError):
            return MoveResult(ok=False, error="cell 必须是 0-8 的整数")
        if cell < 0 or cell > 8:
            return MoveResult(ok=False, error="cell 超出范围 (0-8)")
        if self.board[cell] is not None:
            return MoveResult(ok=False, error="该格已被占用")
        return MoveResult(ok=True)

    def apply(self, player_id: str, move: dict[str, Any]) -> MoveResult:
        check = self.validate(player_id, move)
        if not check.ok:
            return check
        cell = int(move["cell"])
        symbol = self.symbols[player_id]
        self.board[cell] = symbol
        self.move_count += 1

        if self._check_win(symbol):
            self.winner = player_id
        elif self.move_count >= 9:
            self.draw = True
        else:
            # Switch turn
            other = [p.player_id for p in self.players if p.player_id != player_id][0]
            self.current = other
        return MoveResult(ok=True)

    def _check_win(self, symbol: str) -> bool:
        for a, b, c in self.WIN_LINES:
            if self.board[a] == self.board[b] == self.board[c] == symbol:
                return True
        return False

    def view(self, for_player: str | None = None) -> dict[str, Any]:
        # Tic-tac-toe is fully public; for_player kept for API consistency
        seats = [
            {
                "player_id": p.player_id,
                "nickname": p.nickname,
                "seat": p.seat,
                "symbol": self.symbols.get(p.player_id),
            }
            for p in self.players
        ]
        return {
            "game_id": self.game_id,
            "board": list(self.board),
            "current": self.current,
            "your_turn": for_player == self.current if for_player else None,
            "your_symbol": self.symbols.get(for_player) if for_player else None,
            "seats": seats,
            "move_count": self.move_count,
            "winner": self.winner,
            "draw": self.draw,
        }

    def is_over(self) -> GameOverInfo:
        if self.winner:
            nick = self._player_by_id[self.winner].nickname
            return GameOverInfo(
                over=True,
                winner_id=self.winner,
                reason=f"{nick} ({self.symbols[self.winner]}) 获胜！",
            )
        if self.draw:
            return GameOverInfo(over=True, winner_id=None, reason="平局！")
        return GameOverInfo(over=False)

    @staticmethod
    def format_board(board: list[str | None]) -> str:
        """Render board for terminal UI."""
        cells = [c if c else str(i) for i, c in enumerate(board)]
        rows = []
        for r in range(3):
            row = " | ".join(cells[r * 3 : r * 3 + 3])
            rows.append(f" {row} ")
        return "\n---+---+---\n".join(rows)
