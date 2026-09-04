"""python -m boardgame_platform host|client"""

from __future__ import annotations

import sys


def host_main() -> None:
    from boardgame_platform.host import main

    main()


def client_main() -> None:
    from boardgame_platform.client import main

    main()


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("用法:")
        print("  python -m boardgame_platform host [--host 0.0.0.0] [--port 8765]")
        print("  python -m boardgame_platform client [--url ws://127.0.0.1:8765/ws] [-n 昵称]")
        print("  python -m boardgame_platform client --host 公网IP --port 映射端口 -n 昵称")
        sys.exit(0 if len(sys.argv) > 1 else 1)

    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "host":
        from boardgame_platform.host import main as host

        host(rest)
    elif cmd == "client":
        from boardgame_platform.client import main as client

        client(rest)
    else:
        print(f"未知子命令: {cmd}", file=sys.stderr)
        print("请使用 host 或 client", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
