"""Authoritative listen-server (FastAPI + WebSocket + web UI)."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from boardgame_platform.game_api import ensure_builtin_games_loaded, list_games
from boardgame_platform.protocol import MsgType, msg
from boardgame_platform.room import Room, RoomManager, RoomPhase


ensure_builtin_games_loaded()


def web_dir() -> Path:
    """Locate packaged web assets (dev tree or PyInstaller _MEIPASS)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "boardgame_platform" / "web"
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parent / "web"


class ConnectionHub:
    """Track WebSocket connections by player_id."""

    def __init__(self) -> None:
        self.by_player: dict[str, WebSocket] = {}
        self.player_meta: dict[str, dict[str, Any]] = {}

    async def register(self, player_id: str, ws: WebSocket, nickname: str = "") -> None:
        old = self.by_player.get(player_id)
        if old is not None and old is not ws:
            try:
                await old.close(code=4000, reason="replaced")
            except Exception:
                pass
        self.by_player[player_id] = ws
        self.player_meta[player_id] = {"nickname": nickname}

    def unregister(self, player_id: str, ws: WebSocket | None = None) -> None:
        cur = self.by_player.get(player_id)
        if cur is None:
            return
        if ws is not None and cur is not ws:
            return
        self.by_player.pop(player_id, None)

    async def send(self, player_id: str, data: dict[str, Any]) -> None:
        ws = self.by_player.get(player_id)
        if ws is None:
            return
        try:
            await ws.send_json(data)
        except Exception:
            self.unregister(player_id, ws)

    async def broadcast_room(
        self,
        room: Room,
        data: dict[str, Any],
        exclude: str | None = None,
    ) -> None:
        for pid in room.players:
            if exclude and pid == exclude:
                continue
            await self.send(pid, data)

    async def send_state_to_all(self, room: Room, rooms: RoomManager) -> None:
        for pid in room.players:
            state = rooms.filtered_state(room, pid)
            if state is not None:
                await self.send(pid, msg(MsgType.STATE, state=state))


def create_app(rooms: RoomManager | None = None, hub: ConnectionHub | None = None) -> FastAPI:
    rooms = rooms or RoomManager()
    hub = hub or ConnectionHub()
    app = FastAPI(title="Boardgame FRP Platform Host", version="0.1.0")
    app.state.rooms = rooms
    app.state.hub = hub

    assets = web_dir()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/games")
    async def api_games() -> dict[str, Any]:
        return {"games": list_games()}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(assets / "index.html")

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        player_id = secrets.token_hex(8)
        nickname = f"Player-{player_id[:4]}"
        await hub.register(player_id, ws, nickname)
        await ws.send_json(
            msg(
                MsgType.WELCOME,
                player_id=player_id,
                games=list_games(),
                hint="发送 create_room / join_room / list_games 等消息",
            )
        )

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_json(msg(MsgType.ERROR, error="无效 JSON"))
                    continue
                if not isinstance(data, dict) or "type" not in data:
                    await ws.send_json(msg(MsgType.ERROR, error="消息缺少 type"))
                    continue
                await _handle(ws, player_id, data, rooms, hub)
        except WebSocketDisconnect:
            pass
        finally:
            room = rooms.leave(player_id)
            hub.unregister(player_id, ws)
            if room is not None:
                await hub.broadcast_room(
                    room,
                    msg(MsgType.ROOM_UPDATE, room=room.public_snapshot()),
                )

    if assets.is_dir():
        app.mount("/static", StaticFiles(directory=str(assets)), name="static")

    return app


async def _handle(
    ws: WebSocket,
    player_id: str,
    data: dict[str, Any],
    rooms: RoomManager,
    hub: ConnectionHub,
) -> None:
    t = data.get("type")

    async def err(text: str) -> None:
        await ws.send_json(msg(MsgType.ERROR, error=text))

    if t == MsgType.PING.value:
        await ws.send_json(msg(MsgType.PONG))
        return

    if t == MsgType.LIST_GAMES.value:
        await ws.send_json(msg(MsgType.GAMES, games=list_games()))
        return

    if t == MsgType.CREATE_ROOM.value:
        nickname = str(data.get("nickname") or hub.player_meta.get(player_id, {}).get("nickname") or "Host")
        game_id = str(data.get("game_id") or "tictactoe")
        hub.player_meta[player_id] = {"nickname": nickname}
        # Leave previous room if any
        prev = rooms.leave(player_id)
        if prev is not None:
            await hub.broadcast_room(prev, msg(MsgType.ROOM_UPDATE, room=prev.public_snapshot()))
        try:
            room = rooms.create_room(game_id, player_id, nickname)
        except ValueError as e:
            await err(str(e))
            return
        await ws.send_json(
            msg(MsgType.ROOM_CREATED, room=room.public_snapshot(), player_id=player_id)
        )
        return

    if t == MsgType.JOIN_ROOM.value:
        code = str(data.get("code") or "").strip().upper()
        nickname = str(data.get("nickname") or hub.player_meta.get(player_id, {}).get("nickname") or "Guest")
        hub.player_meta[player_id] = {"nickname": nickname}
        if not code:
            await err("缺少房间码 code")
            return
        prev = rooms.leave(player_id)
        if prev is not None:
            await hub.broadcast_room(prev, msg(MsgType.ROOM_UPDATE, room=prev.public_snapshot()))
        try:
            room = rooms.join_room(code, player_id, nickname)
        except ValueError as e:
            await err(str(e))
            return
        await ws.send_json(
            msg(MsgType.ROOM_JOINED, room=room.public_snapshot(), player_id=player_id)
        )
        await hub.broadcast_room(
            room,
            msg(MsgType.ROOM_UPDATE, room=room.public_snapshot()),
            exclude=player_id,
        )
        return

    if t == MsgType.READY.value:
        ready = bool(data.get("ready", True))
        try:
            room = rooms.set_ready(player_id, ready)
        except ValueError as e:
            await err(str(e))
            return
        await hub.broadcast_room(
            room, msg(MsgType.ROOM_UPDATE, room=room.public_snapshot())
        )
        return

    if t == MsgType.START.value:
        try:
            room = rooms.start_game(player_id)
        except ValueError as e:
            await err(str(e))
            return
        await hub.broadcast_room(
            room,
            msg(MsgType.GAME_STARTED, room=room.public_snapshot()),
        )
        await hub.send_state_to_all(room, rooms)
        return

    if t == MsgType.MOVE.value:
        move = data.get("move")
        if not isinstance(move, dict):
            await err("move 必须是对象")
            return
        try:
            room = rooms.apply_move(player_id, move)
        except ValueError as e:
            await err(str(e))
            return
        await hub.send_state_to_all(room, rooms)
        if room.phase == RoomPhase.FINISHED and room.game is not None:
            over = room.game.is_over()
            await hub.broadcast_room(
                room,
                msg(
                    MsgType.GAME_OVER,
                    winner_id=over.winner_id,
                    reason=over.reason,
                    room=room.public_snapshot(),
                ),
            )
        return

    if t == MsgType.LEAVE.value:
        room = rooms.leave(player_id)
        await ws.send_json(msg(MsgType.ROOM_UPDATE, room=None, left=True))
        if room is not None:
            await hub.broadcast_room(
                room, msg(MsgType.ROOM_UPDATE, room=room.public_snapshot())
            )
        return

    await err(f"未知消息类型: {t}")


def run_host(
    host: str = "0.0.0.0",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    import uvicorn

    app = create_app()
    local_hint = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    ui_url = f"http://{local_hint}:{port}/"
    print("=" * 60)
    print("  boardgame-frp-platform  主机 (Listen Server)")
    print("=" * 60)
    print(f"  网页界面:        {ui_url}")
    print(f"  本地 WebSocket:  ws://{local_hint}:{port}/ws")
    print(f"  健康检查:        http://{local_hint}:{port}/health")
    print()
    print("  本机用浏览器打开上面的网页（可开两个标签互玩）。")
    print("  异地好友不能打开 127.0.0.1；请用 OpenFrp/frp 映射本机端口，")
    print("  让好友访问 http://公网地址:端口/ 再输入房间码。详见 docs/frp-zh.md")
    print("=" * 60)

    if open_browser:
        def _open() -> None:
            time.sleep(0.9)
            try:
                webbrowser.open(ui_url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="启动棋盘游戏主机 (listen-server)")
    p.add_argument("--host", default="0.0.0.0", help="绑定地址 (默认 0.0.0.0)")
    p.add_argument("--port", type=int, default=8765, help="端口 (默认 8765)")
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="不自动打开浏览器界面",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_argparser().parse_args(argv)
    run_host(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
