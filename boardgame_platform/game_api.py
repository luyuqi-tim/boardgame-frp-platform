"""Pluggable game interface for turn-based board games."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlayerInfo:
    player_id: str
    nickname: str
    seat: int = 0


@dataclass
class MoveResult:
    ok: bool
    error: str | None = None
    state_changed: bool = True


@dataclass
class GameOverInfo:
    over: bool
    winner_id: str | None = None
    reason: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


class GamePlugin(ABC):
    """Base class for pluggable board games.

    Lifecycle:
      1. Host creates instance via registry with player list.
      2. setup() initializes authoritative state.
      3. Clients send moves → validate() → apply().
      4. view(for_player) returns filtered state per player.
      5. is_over() decides when the match ends.
    """

    game_id: str = "base"
    display_name: str = "Base Game"
    min_players: int = 2
    max_players: int = 2
    description: str = ""

    def __init__(self, players: list[PlayerInfo]) -> None:
        self.players = list(players)
        self._player_by_id = {p.player_id: p for p in self.players}

    @abstractmethod
    def setup(self) -> None:
        """Initialize authoritative game state after players are seated."""

    @abstractmethod
    def validate(self, player_id: str, move: dict[str, Any]) -> MoveResult:
        """Validate a move without mutating state. Return ok=False on failure."""

    @abstractmethod
    def apply(self, player_id: str, move: dict[str, Any]) -> MoveResult:
        """Apply a validated move. Callers should validate first or re-check."""

    @abstractmethod
    def view(self, for_player: str | None = None) -> dict[str, Any]:
        """Return state visible to ``for_player`` (None = full/public view)."""

    @abstractmethod
    def is_over(self) -> GameOverInfo:
        """Whether the game has ended and who won (if anyone)."""

    def meta(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "display_name": self.display_name,
            "min_players": self.min_players,
            "max_players": self.max_players,
            "description": self.description,
        }


# Registry -----------------------------------------------------------------

_REGISTRY: dict[str, type[GamePlugin]] = {}


def register_game(cls: type[GamePlugin]) -> type[GamePlugin]:
    """Decorator / helper to register a game plugin class."""
    if not getattr(cls, "game_id", None):
        raise ValueError(f"Game plugin {cls} missing game_id")
    _REGISTRY[cls.game_id] = cls
    return cls


def get_game(game_id: str) -> type[GamePlugin] | None:
    return _REGISTRY.get(game_id)


def list_games() -> list[dict[str, Any]]:
    return [
        {
            "game_id": g.game_id,
            "display_name": g.display_name,
            "min_players": g.min_players,
            "max_players": g.max_players,
            "description": g.description,
        }
        for g in _REGISTRY.values()
    ]


def ensure_builtin_games_loaded() -> None:
    """Import built-in games so they self-register."""
    from boardgame_platform.games import tictactoe  # noqa: F401
