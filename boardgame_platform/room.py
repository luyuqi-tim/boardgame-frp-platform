"""Room manager: codes, lobby, players, and game lifecycle."""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from boardgame_platform.game_api import (
    GamePlugin,
    PlayerInfo,
    get_game,
)


class RoomPhase(str, Enum):
    LOBBY = "lobby"
    PLAYING = "playing"
    FINISHED = "finished"


CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_room_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


@dataclass
class RoomPlayer:
    player_id: str
    nickname: str
    ready: bool = False
    connected: bool = True


@dataclass
class Room:
    code: str
    game_id: str
    host_player_id: str
    players: dict[str, RoomPlayer] = field(default_factory=dict)
    phase: RoomPhase = RoomPhase.LOBBY
    game: GamePlugin | None = None
    max_players: int = 2
    min_players: int = 2

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "game_id": self.game_id,
            "phase": self.phase.value,
            "host_player_id": self.host_player_id,
            "min_players": self.min_players,
            "max_players": self.max_players,
            "players": [
                {
                    "player_id": p.player_id,
                    "nickname": p.nickname,
                    "ready": p.ready,
                    "connected": p.connected,
                    "is_host": p.player_id == self.host_player_id,
                }
                for p in self.players.values()
            ],
        }


class RoomManager:
    """In-memory rooms keyed by short code."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._player_room: dict[str, str] = {}  # player_id → room code

    def create_room(
        self,
        game_id: str,
        host_player_id: str,
        host_nickname: str,
    ) -> Room:
        cls = get_game(game_id)
        if cls is None:
            raise ValueError(f"未知游戏: {game_id}")

        # Unique code
        for _ in range(50):
            code = generate_room_code()
            if code not in self._rooms:
                break
        else:
            raise RuntimeError("无法生成唯一房间码")

        room = Room(
            code=code,
            game_id=game_id,
            host_player_id=host_player_id,
            min_players=cls.min_players,
            max_players=cls.max_players,
        )
        room.players[host_player_id] = RoomPlayer(
            player_id=host_player_id,
            nickname=host_nickname,
            ready=False,
        )
        self._rooms[code] = room
        self._player_room[host_player_id] = code
        return room

    def get(self, code: str) -> Room | None:
        return self._rooms.get(code.upper())

    def room_of(self, player_id: str) -> Room | None:
        code = self._player_room.get(player_id)
        return self._rooms.get(code) if code else None

    def join_room(
        self,
        code: str,
        player_id: str,
        nickname: str,
    ) -> Room:
        room = self.get(code)
        if room is None:
            raise ValueError("房间不存在")
        if room.phase != RoomPhase.LOBBY:
            raise ValueError("游戏已开始，无法加入")
        if player_id in room.players:
            # Reconnect
            room.players[player_id].connected = True
            room.players[player_id].nickname = nickname
            self._player_room[player_id] = room.code
            return room
        if len(room.players) >= room.max_players:
            raise ValueError("房间已满")
        room.players[player_id] = RoomPlayer(
            player_id=player_id,
            nickname=nickname,
            ready=False,
        )
        self._player_room[player_id] = room.code
        return room

    def set_ready(self, player_id: str, ready: bool = True) -> Room:
        room = self.room_of(player_id)
        if room is None:
            raise ValueError("你不在任何房间")
        if room.phase != RoomPhase.LOBBY:
            raise ValueError("游戏已开始")
        player = room.players.get(player_id)
        if player is None:
            raise ValueError("玩家不在房间")
        player.ready = ready
        return room

    def start_game(self, player_id: str) -> Room:
        room = self.room_of(player_id)
        if room is None:
            raise ValueError("你不在任何房间")
        if player_id != room.host_player_id:
            raise ValueError("只有房主可以开始游戏")
        if room.phase != RoomPhase.LOBBY:
            raise ValueError("游戏已开始或已结束")
        if len(room.players) < room.min_players:
            raise ValueError(f"至少需要 {room.min_players} 名玩家")
        not_ready = [p.nickname for p in room.players.values() if not p.ready]
        if not_ready:
            raise ValueError(f"以下玩家尚未准备: {', '.join(not_ready)}")

        cls = get_game(room.game_id)
        if cls is None:
            raise ValueError(f"未知游戏: {room.game_id}")

        ordered = list(room.players.values())
        infos = [
            PlayerInfo(player_id=p.player_id, nickname=p.nickname, seat=i)
            for i, p in enumerate(ordered)
        ]
        game = cls(infos)
        game.setup()
        room.game = game
        room.phase = RoomPhase.PLAYING
        return room

    def apply_move(self, player_id: str, move: dict[str, Any]) -> Room:
        room = self.room_of(player_id)
        if room is None:
            raise ValueError("你不在任何房间")
        if room.phase != RoomPhase.PLAYING or room.game is None:
            raise ValueError("当前没有进行中的对局")
        result = room.game.apply(player_id, move)
        if not result.ok:
            raise ValueError(result.error or "非法走子")
        over = room.game.is_over()
        if over.over:
            room.phase = RoomPhase.FINISHED
        return room

    def leave(self, player_id: str) -> Room | None:
        room = self.room_of(player_id)
        if room is None:
            return None
        self._player_room.pop(player_id, None)
        player = room.players.get(player_id)
        if player:
            player.connected = False
            if room.phase == RoomPhase.LOBBY:
                room.players.pop(player_id, None)
                if player_id == room.host_player_id and room.players:
                    # Transfer host
                    new_host = next(iter(room.players.values()))
                    room.host_player_id = new_host.player_id
                elif not room.players:
                    self._rooms.pop(room.code, None)
                    return None
            elif room.phase == RoomPhase.PLAYING:
                # Mark disconnected; game continues until explicit forfeit logic
                pass
        return room

    def filtered_state(self, room: Room, for_player: str) -> dict[str, Any] | None:
        if room.game is None:
            return None
        return room.game.view(for_player=for_player)
