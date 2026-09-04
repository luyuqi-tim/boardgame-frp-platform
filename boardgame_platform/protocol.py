"""JSON-over-WebSocket message types for the board-game platform."""

from __future__ import annotations

from enum import Enum
from typing import Any


class MsgType(str, Enum):
    # Client → Host
    CREATE_ROOM = "create_room"
    JOIN_ROOM = "join_room"
    READY = "ready"
    START = "start"
    MOVE = "move"
    LEAVE = "leave"
    LIST_GAMES = "list_games"
    PING = "ping"

    # Host → Client
    WELCOME = "welcome"
    ROOM_CREATED = "room_created"
    ROOM_JOINED = "room_joined"
    ROOM_UPDATE = "room_update"
    GAME_STARTED = "game_started"
    STATE = "state"
    ERROR = "error"
    PONG = "pong"
    GAMES = "games"
    GAME_OVER = "game_over"


def msg(type_: MsgType | str, **payload: Any) -> dict[str, Any]:
    """Build a protocol message dict."""
    t = type_.value if isinstance(type_, MsgType) else type_
    return {"type": t, **payload}
