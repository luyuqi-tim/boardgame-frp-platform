# boardgame-frp-platform

PC 端多人**回合制棋盘游戏**平台：房主 Listen-Server + **frp 仅做连通**，对局逻辑永不跑在 frps 上。

- 用短**房间码**或主机地址加入
- 大厅：选游戏 → 创建房间 / 输入房间码加入
- 插件化游戏接口，便于后续扩展
- 零付费云依赖（标准库 + FastAPI / WebSocket）

## 架构

```
┌─────────────┐     WebSocket      ┌──────────────────────┐
│  客户端 A   │◄──────────────────►│  房主 PC             │
│  (终端 UI)  │                    │  boardgame host      │
└─────────────┘                    │  · 房间管理          │
                                   │  · 权威游戏逻辑      │
┌─────────────┐     WebSocket      │  · 按玩家过滤状态    │
│  客户端 B   │◄──────────────────►│                      │
└─────────────┘                    └──────────┬───────────┘
       ▲                                      │ 可选
       │         公网不可达时                  ▼
       └────────── frp / OpenFrp 隧道 ─── 仅转发 TCP/WS
                    （无游戏状态）
```

## 快速开始

### 环境

- Python **3.11+**
- 建议使用虚拟环境

```bash
cd boardgame-frp-platform
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
# 或: pip install -r requirements.txt
```

### 本机双终端打完一局井字棋

**终端 1 — 主机：**

```bash
python -m boardgame_platform host --port 8765
```

会打印本地地址，例如 `ws://127.0.0.1:8765/ws`。

**终端 2 — 房主客户端：**

```bash
python -m boardgame_platform client -n Alice
# 选 1 创建房间 → 游戏默认 tictactoe → 记下房间码 → 输入 ready
# 等 Bob 准备后输入 start
```

**终端 3 — 另一客户端：**

```bash
python -m boardgame_platform client -n Bob
# 选 2 加入 → 输入房间码 → ready
# 对局中输入 0-8 落子
```

棋盘示意（空位显示编号）：

```
 0 | 1 | 2
---+---+---
 3 | 4 | 5
---+---+---
 6 | 7 | 8
```

X（先手，通常为房主座位 0）与 O 轮流落子，三连或填满结束。


## Windows 免安装包（exe）

不装 Python 也可以玩。仓库用 GitHub Actions 在 Windows 上自动打包：

1. 打开仓库 **Actions** → **Build Windows EXE** → **Run workflow**
2. 跑完后进入该次运行 → **Artifacts** → 下载 `boardgame-windows-exe`
3. 解压得到：
   - `BoardGameHost.exe` — 建房者运行（开主机）
   - `BoardGameClient.exe` — 所有人运行（创建/加入房间）

本机双击流程（局域网先测）：

1. 建房者双击 `BoardGameHost.exe`（默认端口 8765，窗口别关）
2. 两人各开 `BoardGameClient.exe`，一人创建房间、一人输入房间码加入

异地：主机仍要配合 frp（见 `docs/frp-zh.md`），客户端连接时填穿透后的地址。

也可在已装 Python 的 Windows 上手动打包：

```powershell
.\packaging\build_windows.ps1
```

产物在 `dist\`。

### 远程联机（frp）

详见 **[docs/frp-zh.md](docs/frp-zh.md)**（OpenFrp + 自建 frps）。

简要步骤：

1. 房主启动 `python -m boardgame_platform host`
2. 用 OpenFrp / frpc 把本机 `8765` 映射到公网
3. 创建房间拿到房间码
4. 分享：`公网host:port` + 房间码
5. 好友：`python -m boardgame_platform client --host <公网> --port <映射端口> -n 昵称`

示例配置：`deploy/frpc.toml.example`。

## CLI

```bash
python -m boardgame_platform host [--host 0.0.0.0] [--port 8765]
python -m boardgame_platform client [--url ws://127.0.0.1:8765/ws] [-n 昵称]
python -m boardgame_platform client --host 1.2.3.4 --port 18765 -n 小明
```

也可安装后使用入口脚本：`boardgame-host` / `boardgame-client`。

## 协议概要（JSON over WebSocket）

客户端 → 主机：`create_room` / `join_room` / `ready` / `start` / `move` / `leave` / `list_games` / `ping`

主机 → 客户端：`welcome` / `room_created` / `room_joined` / `room_update` / `game_started` / `state` / `game_over` / `error` / `pong` / `games`

`state` 经 `GamePlugin.view(for_player=...)` **按玩家过滤**后下发（井字棋为公开信息，接口仍统一）。

## 如何新增一款游戏

1. 在 `boardgame_platform/games/` 新建模块，实现 `GamePlugin`：
   - `setup` / `validate` / `apply` / `view` / `is_over`
   - 设置 `game_id`、`display_name`、`min_players`、`max_players`
2. 使用 `@register_game` 装饰器注册
3. 在 `game_api.ensure_builtin_games_loaded()` 中 import 该模块
4. 客户端创建房间时指定 `game_id`

参考实现：`boardgame_platform/games/tictactoe.py`。

## 测试

```bash
pytest -q
```

## 目录结构

```
boardgame-frp-platform/
├── boardgame_platform/
│   ├── __main__.py          # host / client 入口
│   ├── host.py              # FastAPI + WebSocket 权威主机
│   ├── client.py            # 终端客户端
│   ├── room.py              # 房间码与大厅
│   ├── protocol.py          # 消息类型
│   ├── game_api.py          # 游戏插件接口与注册表
│   └── games/
│       └── tictactoe.py     # 可玩演示
├── deploy/frpc.toml.example
├── docs/frp-zh.md
├── tests/
├── pyproject.toml
├── requirements.txt
├── LICENSE                  # MIT
└── README.md
```

## 许可证

MIT — 见 [LICENSE](LICENSE)。
