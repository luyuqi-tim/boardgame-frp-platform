"""Tests for RoomManager."""

import pytest

from boardgame_platform.game_api import ensure_builtin_games_loaded
from boardgame_platform.room import RoomManager, RoomPhase, generate_room_code


ensure_builtin_games_loaded()


def test_generate_room_code() -> None:
    code = generate_room_code(6)
    assert len(code) == 6
    assert code.isalnum()
    assert code.isupper() or any(c.isdigit() for c in code)


def test_create_join_ready_start_move() -> None:
    rm = RoomManager()
    room = rm.create_room("tictactoe", "host1", "Host")
    assert len(room.code) == 6
    assert room.phase == RoomPhase.LOBBY

    room = rm.join_room(room.code, "guest1", "Guest")
    assert len(room.players) == 2

    rm.set_ready("host1", True)
    rm.set_ready("guest1", True)
    room = rm.start_game("host1")
    assert room.phase == RoomPhase.PLAYING
    assert room.game is not None

    room = rm.apply_move("host1", {"cell": 4})
    state = rm.filtered_state(room, "guest1")
    assert state is not None
    assert state["board"][4] == "X"
    assert state["your_turn"] is True


def test_unknown_game() -> None:
    rm = RoomManager()
    with pytest.raises(ValueError, match="未知游戏"):
        rm.create_room("nope", "h", "H")


def test_start_requires_host_and_ready() -> None:
    rm = RoomManager()
    room = rm.create_room("tictactoe", "h", "H")
    rm.join_room(room.code, "g", "G")
    with pytest.raises(ValueError, match="房主"):
        rm.start_game("g")
    with pytest.raises(ValueError, match="准备"):
        rm.start_game("h")


def test_leave_lobby_transfers_host() -> None:
    rm = RoomManager()
    room = rm.create_room("tictactoe", "h", "H")
    rm.join_room(room.code, "g", "G")
    left = rm.leave("h")
    assert left is not None
    assert left.host_player_id == "g"
    assert "h" not in left.players
