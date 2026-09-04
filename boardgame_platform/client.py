"""Terminal WebSocket client for the board-game platform."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from boardgame_platform.games.tictactoe import TicTacToe
from boardgame_platform.protocol import MsgType


try:
    import websockets
    from websockets.asyncio.client import connect as ws_connect
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore
    ws_connect = None  # type: ignore


class TerminalClient:
    def __init__(self, url: str, nickname: str) -> None:
        self.url = url
        self.nickname = nickname
        self.player_id: str | None = None
        self.room: dict[str, Any] | None = None
        self.state: dict[str, Any] | None = None
        self.games: list[dict[str, Any]] = []
        self._ws: Any = None
        self._inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._game_over_reason: str | None = None
        self._running = True

    async def send(self, type_: str, **payload: Any) -> None:
        assert self._ws is not None
        await self._ws.send(json.dumps({"type": type_, **payload}, ensure_ascii=False))

    async def _reader(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._inbox.put(data)
        except Exception:
            self._running = False
            await self._inbox.put({"type": "_closed"})

    async def wait_msg(self, *types: str, timeout: float | None = 60.0) -> dict[str, Any]:
        wanted = set(types)
        while True:
            try:
                if timeout is None:
                    data = await self._inbox.get()
                else:
                    data = await asyncio.wait_for(self._inbox.get(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(f"等待消息超时: {wanted or 'any'}") from None
            t = data.get("type")
            if t == MsgType.ERROR.value:
                # Surface errors immediately when waiting for something else
                print(f"\n[错误] {data.get('error')}")
                if not wanted or MsgType.ERROR.value in wanted:
                    return data
                continue
            if not wanted or t in wanted:
                return data
            # Keep processing side-effects for unsolicited updates
            self._apply_side_effect(data)

    def _apply_side_effect(self, data: dict[str, Any]) -> None:
        t = data.get("type")
        if t == MsgType.ROOM_UPDATE.value:
            self.room = data.get("room")
        elif t == MsgType.STATE.value:
            self.state = data.get("state")
        elif t == MsgType.GAME_OVER.value:
            self._game_over_reason = data.get("reason")
            if data.get("room"):
                self.room = data["room"]
        elif t == MsgType.GAME_STARTED.value:
            if data.get("room"):
                self.room = data["room"]

    def _print_room(self) -> None:
        if not self.room:
            print("(不在房间中)")
            return
        print(f"\n── 房间 {self.room.get('code')} | 游戏 {self.room.get('game_id')} | 阶段 {self.room.get('phase')} ──")
        for p in self.room.get("players", []):
            flags = []
            if p.get("is_host"):
                flags.append("房主")
            if p.get("ready"):
                flags.append("已准备")
            if not p.get("connected"):
                flags.append("离线")
            mark = " *" if p.get("player_id") == self.player_id else ""
            flag_s = f" [{', '.join(flags)}]" if flags else ""
            print(f"  - {p.get('nickname')}{mark}{flag_s}")

    def _print_board(self) -> None:
        if not self.state:
            return
        board = self.state.get("board")
        if board is None:
            print(json.dumps(self.state, ensure_ascii=False, indent=2))
            return
        print()
        print(TicTacToe.format_board(board))
        print()
        if self.state.get("your_symbol"):
            turn = "你的回合" if self.state.get("your_turn") else "对手回合"
            print(f"你是 {self.state['your_symbol']}  |  {turn}")
        cur = self.state.get("current")
        seats = {s["player_id"]: s for s in self.state.get("seats", [])}
        if cur and cur in seats:
            print(f"当前行动: {seats[cur]['nickname']} ({seats[cur].get('symbol')})")

    async def run_interactive(self) -> None:
        if ws_connect is None:
            print("缺少 websockets 库，请先: pip install websockets", file=sys.stderr)
            sys.exit(1)

        print(f"正在连接 {self.url} ...")
        async with ws_connect(self.url) as ws:
            self._ws = ws
            reader = asyncio.create_task(self._reader())
            try:
                welcome = await self.wait_msg(MsgType.WELCOME.value)
                self.player_id = welcome.get("player_id")
                self.games = welcome.get("games") or []
                print(f"已连接。你的 ID: {self.player_id}")
                print("可用游戏:")
                for g in self.games:
                    print(
                        f"  [{g['game_id']}] {g['display_name']} "
                        f"({g['min_players']}-{g['max_players']}人) — {g.get('description', '')}"
                    )

                await self._lobby_flow()
                if self.room and self.room.get("phase") in ("playing", "finished"):
                    await self._play_loop()
                elif self.room:
                    # Wait for start then play
                    await self._wait_start_and_play()
            finally:
                self._running = False
                reader.cancel()
                try:
                    await reader
                except asyncio.CancelledError:
                    pass

    async def _lobby_flow(self) -> None:
        print("\n请选择:")
        print("  1) 创建房间 (默认井字棋)")
        print("  2) 加入房间 (输入房间码)")
        choice = (await asyncio.to_thread(input, "> ")).strip() or "1"

        if choice.startswith("2"):
            code = (await asyncio.to_thread(input, "房间码: ")).strip().upper()
            await self.send(MsgType.JOIN_ROOM.value, code=code, nickname=self.nickname)
            data = await self.wait_msg(MsgType.ROOM_JOINED.value, MsgType.ERROR.value)
            if data.get("type") == MsgType.ERROR.value:
                raise SystemExit(1)
            self.room = data.get("room")
            print(f"已加入房间 {self.room.get('code')}")
        else:
            game_id = "tictactoe"
            if self.games:
                gid = (await asyncio.to_thread(input, f"游戏 ID [{game_id}]: ")).strip()
                if gid:
                    game_id = gid
            await self.send(
                MsgType.CREATE_ROOM.value,
                game_id=game_id,
                nickname=self.nickname,
            )
            data = await self.wait_msg(MsgType.ROOM_CREATED.value, MsgType.ERROR.value)
            if data.get("type") == MsgType.ERROR.value:
                raise SystemExit(1)
            self.room = data.get("room")
            print(f"\n★ 房间已创建！房间码: {self.room.get('code')}")
            print("  把房间码分享给好友；若走 frp，同时分享公网 host:port。")

        self._print_room()
        print("\n输入 ready 准备，房主输入 start 开始，leave 离开，status 查看房间。")

        is_host = False
        if self.room:
            for p in self.room.get("players", []):
                if p.get("player_id") == self.player_id and p.get("is_host"):
                    is_host = True

        while self._running and self.room and self.room.get("phase") == "lobby":
            # Drain any pending room updates
            while not self._inbox.empty():
                data = self._inbox.get_nowait()
                self._apply_side_effect(data)
                if data.get("type") == MsgType.GAME_STARTED.value:
                    print("\n游戏开始！")
                    return
                if data.get("type") == MsgType.ROOM_UPDATE.value:
                    self._print_room()

            cmd = (await asyncio.to_thread(input, "lobby> ")).strip().lower()
            if not cmd:
                continue
            if cmd in ("ready", "r"):
                await self.send(MsgType.READY.value, ready=True)
                data = await self.wait_msg(MsgType.ROOM_UPDATE.value, MsgType.ERROR.value)
                self._apply_side_effect(data)
                self._print_room()
            elif cmd in ("unready", "u"):
                await self.send(MsgType.READY.value, ready=False)
                data = await self.wait_msg(MsgType.ROOM_UPDATE.value, MsgType.ERROR.value)
                self._apply_side_effect(data)
                self._print_room()
            elif cmd in ("start", "s"):
                if not is_host:
                    print("只有房主可以开始。")
                    continue
                await self.send(MsgType.START.value)
                data = await self.wait_msg(
                    MsgType.GAME_STARTED.value,
                    MsgType.ERROR.value,
                    MsgType.STATE.value,
                )
                if data.get("type") == MsgType.ERROR.value:
                    continue
                self._apply_side_effect(data)
                # May get STATE next
                if data.get("type") != MsgType.STATE.value:
                    try:
                        st = await self.wait_msg(MsgType.STATE.value, timeout=5.0)
                        self._apply_side_effect(st)
                    except TimeoutError:
                        pass
                print("\n游戏开始！")
                return
            elif cmd in ("status", "st"):
                self._print_room()
            elif cmd in ("leave", "quit", "q"):
                await self.send(MsgType.LEAVE.value)
                print("已离开房间。")
                self.room = None
                return
            elif cmd in ("help", "h", "?"):
                print("命令: ready / unready / start / status / leave")
            else:
                print("未知命令。输入 help 查看。")

    async def _wait_start_and_play(self) -> None:
        print("等待房主开始...")
        while self._running:
            data = await self.wait_msg(
                MsgType.GAME_STARTED.value,
                MsgType.STATE.value,
                MsgType.ROOM_UPDATE.value,
                MsgType.GAME_OVER.value,
                timeout=None,
            )
            self._apply_side_effect(data)
            if data.get("type") == MsgType.ROOM_UPDATE.value:
                self._print_room()
            if data.get("type") in (MsgType.GAME_STARTED.value, MsgType.STATE.value):
                if data.get("type") == MsgType.GAME_STARTED.value:
                    try:
                        st = await self.wait_msg(MsgType.STATE.value, timeout=5.0)
                        self._apply_side_effect(st)
                    except TimeoutError:
                        pass
                await self._play_loop()
                return

    async def _play_loop(self) -> None:
        print("\n═══ 对局中 ═══")
        print("输入 0-8 落子（对应棋盘格子编号），或 quit 退出。")
        self._print_board()

        while self._running:
            # Drain updates
            while not self._inbox.empty():
                data = self._inbox.get_nowait()
                self._apply_side_effect(data)
                if data.get("type") == MsgType.STATE.value:
                    self._print_board()
                if data.get("type") == MsgType.GAME_OVER.value:
                    print(f"\n★ {self._game_over_reason or data.get('reason')}")
                    self._print_board()
                    return

            if self._game_over_reason:
                print(f"\n★ {self._game_over_reason}")
                return

            if self.state and self.state.get("winner") or (self.state and self.state.get("draw")):
                over_reason = "平局" if self.state.get("draw") else "有人获胜"
                print(f"\n游戏结束 ({over_reason})")
                return

            your_turn = bool(self.state and self.state.get("your_turn"))
            prompt = "你的回合，输入格子 0-8> " if your_turn else "(等待对手，也可输入 refresh/quit)> "

            # Concurrent wait: user input OR incoming message
            input_task = asyncio.create_task(asyncio.to_thread(input, prompt))
            msg_task = asyncio.create_task(self._inbox.get())
            done, pending = await asyncio.wait(
                {input_task, msg_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

            if msg_task in done:
                data = msg_task.result()
                self._apply_side_effect(data)
                if data.get("type") == MsgType.STATE.value:
                    self._print_board()
                if data.get("type") == MsgType.GAME_OVER.value:
                    print(f"\n★ {self._game_over_reason or data.get('reason')}")
                    self._print_board()
                    return
                # If input also somehow finished, ignore for next loop
                if input_task in done:
                    try:
                        input_task.result()
                    except Exception:
                        pass
                continue

            # User typed something
            line = input_task.result().strip().lower()
            if not line:
                continue
            if line in ("quit", "q", "leave"):
                await self.send(MsgType.LEAVE.value)
                print("已离开。")
                return
            if line in ("refresh", "r", "status"):
                self._print_board()
                continue
            if not your_turn:
                print("还没轮到你。")
                continue
            try:
                cell = int(line)
            except ValueError:
                print("请输入 0-8 的数字。")
                continue
            await self.send(MsgType.MOVE.value, move={"cell": cell})
            data = await self.wait_msg(
                MsgType.STATE.value,
                MsgType.GAME_OVER.value,
                MsgType.ERROR.value,
            )
            if data.get("type") == MsgType.ERROR.value:
                continue
            self._apply_side_effect(data)
            self._print_board()
            if data.get("type") == MsgType.GAME_OVER.value or self._game_over_reason:
                print(f"\n★ {self._game_over_reason or data.get('reason')}")
                return


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="棋盘游戏终端客户端")
    p.add_argument(
        "--url",
        default="ws://127.0.0.1:8765/ws",
        help="主机 WebSocket 地址 (默认 ws://127.0.0.1:8765/ws)",
    )
    p.add_argument("--nickname", "-n", default="", help="昵称")
    p.add_argument("--host", default="", help="主机地址，将拼成 ws://HOST:PORT/ws")
    p.add_argument("--port", type=int, default=8765, help="与 --host 合用")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_argparser().parse_args(argv)
    url = args.url
    if args.host:
        url = f"ws://{args.host}:{args.port}/ws"
    nickname = args.nickname.strip()
    if not nickname:
        nickname = input("请输入昵称: ").strip() or "Player"
    try:
        asyncio.run(TerminalClient(url=url, nickname=nickname).run_interactive())
    except KeyboardInterrupt:
        print("\n再见。")


if __name__ == "__main__":
    main()
