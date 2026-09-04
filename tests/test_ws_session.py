"""WebSocket: start must not emit game_over; session reconnect restores player."""

from __future__ import annotations

from fastapi.testclient import TestClient

from boardgame_platform.host import ConnectionHub, create_app
from boardgame_platform.room import RoomManager, RoomPhase


def _recv_types(ws, n: int) -> list[dict]:
    out = []
    for _ in range(n):
        out.append(ws.receive_json())
    return out


def _expect_type(msgs: list[dict], typ: str) -> dict:
    for m in msgs:
        if m.get("type") == typ:
            return m
    raise AssertionError(f"expected {typ} in {[m.get('type') for m in msgs]}")


def test_start_does_not_emit_game_over() -> None:
    rooms = RoomManager()
    hub = ConnectionHub()
    client = TestClient(create_app(rooms, hub))
    with client.websocket_connect("/ws?session_id=start-a") as ws_a:
        with client.websocket_connect("/ws?session_id=start-b") as ws_b:
            assert ws_a.receive_json()["type"] == "welcome"
            assert ws_b.receive_json()["type"] == "welcome"

            ws_a.send_json(
                {"type": "create_room", "game_id": "tictactoe", "nickname": "Alice"}
            )
            created = ws_a.receive_json()
            assert created["type"] == "room_created"
            code = created["room"]["code"]

            ws_b.send_json({"type": "join_room", "code": code, "nickname": "Bob"})
            joined = ws_b.receive_json()
            assert joined["type"] == "room_joined"
            # host gets room_update for join
            assert ws_a.receive_json()["type"] == "room_update"

            ws_a.send_json({"type": "ready", "ready": True})
            # both get room_update
            assert ws_a.receive_json()["type"] == "room_update"
            assert ws_b.receive_json()["type"] == "room_update"

            ws_b.send_json({"type": "ready", "ready": True})
            assert ws_a.receive_json()["type"] == "room_update"
            assert ws_b.receive_json()["type"] == "room_update"

            ws_a.send_json({"type": "start"})
            # Each player: game_started + state (order: broadcast game_started then state each)
            msgs_a = _recv_types(ws_a, 2)
            msgs_b = _recv_types(ws_b, 2)
            types_a = [m["type"] for m in msgs_a]
            types_b = [m["type"] for m in msgs_b]
            assert "game_started" in types_a
            assert "state" in types_a
            assert "game_over" not in types_a
            assert "game_over" not in types_b

            state = _expect_type(msgs_a, "state")["state"]
            assert state.get("winner") in (None, "")
            assert not state.get("draw")
            assert state.get("move_count", 0) == 0


def test_session_reconnect_restores_player() -> None:
    rooms = RoomManager()
    hub = ConnectionHub()
    client = TestClient(create_app(rooms, hub))

    with client.websocket_connect("/ws?session_id=persist-1") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        pid = welcome["player_id"]
        assert welcome.get("session_id") == "persist-1"
        ws.send_json(
            {"type": "create_room", "game_id": "tictactoe", "nickname": "Hosty"}
        )
        created = ws.receive_json()
        assert created["type"] == "room_created"
        code = created["room"]["code"]

    room = rooms.room_of(pid)
    assert room is not None
    assert room.code == code
    assert pid in room.players
    assert room.players[pid].connected is False
    assert hub.player_for_session("persist-1") == pid

    with client.websocket_connect("/ws?session_id=persist-1") as ws2:
        welcome2 = ws2.receive_json()
        assert welcome2["player_id"] == pid
        assert welcome2.get("restored") is True
        assert welcome2.get("room") is not None
        assert welcome2["room"]["code"] == code
        assert rooms.room_of(pid).players[pid].connected is True


def test_session_reconnect_mid_game_sends_state() -> None:
    rooms = RoomManager()
    hub = ConnectionHub()
    client = TestClient(create_app(rooms, hub))

    with client.websocket_connect("/ws?session_id=mg-a") as ws_a:
        with client.websocket_connect("/ws?session_id=mg-b") as ws_b:
            wa = ws_a.receive_json()
            ws_b.receive_json()
            pid_a = wa["player_id"]

            ws_a.send_json(
                {"type": "create_room", "game_id": "tictactoe", "nickname": "A"}
            )
            code = ws_a.receive_json()["room"]["code"]
            ws_b.send_json({"type": "join_room", "code": code, "nickname": "B"})
            assert ws_b.receive_json()["type"] == "room_joined"
            assert ws_a.receive_json()["type"] == "room_update"

            ws_a.send_json({"type": "ready", "ready": True})
            ws_a.receive_json()
            ws_b.receive_json()
            ws_b.send_json({"type": "ready", "ready": True})
            ws_a.receive_json()
            ws_b.receive_json()

            ws_a.send_json({"type": "start"})
            msgs = _recv_types(ws_a, 2)
            assert rooms.room_of(pid_a).phase == RoomPhase.PLAYING
            assert "game_over" not in [m["type"] for m in msgs]

    assert rooms.room_of(pid_a).players[pid_a].connected is False

    with client.websocket_connect("/ws?session_id=mg-a") as ws_a2:
        w = ws_a2.receive_json()
        assert w["player_id"] == pid_a
        assert w.get("room", {}).get("phase") == "playing"
        nxt = ws_a2.receive_json()
        assert nxt["type"] == "state"
        assert nxt["state"]["move_count"] == 0
