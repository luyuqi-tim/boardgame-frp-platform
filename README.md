# boardgame-frp-platform

PC 端多人**回合制棋盘游戏**平台：房主 Listen-Server + **frp 仅做连通**，对局逻辑永不跑在 frps 上。

- **浏览器网页界面**（深色大厅、创建/加入房间、鼠标点棋盘）
- 用短**房间码**或主机地址加入
- 插件化游戏接口，便于后续扩展
- 零付费云依赖（标准库 + FastAPI / WebSocket）
- 终端客户端仍可用（高级选项）

## 架构

```
┌─────────────┐     HTTP + WS      ┌──────────────────────┐
│  浏览器 A   │◄──────────────────►│  房主 PC             │
│  (网页 UI)  │                    │  boardgame host      │
└─────────────┘                    │  · 静态网页          │
                                   │  · 房间管理          │
┌─────────────┐     HTTP + WS      │  · 权威游戏逻辑      │
│  浏览器 B   │◄──────────────────►│  · 按玩家过滤状态    │
└─────────────┘                    └──────────┬───────────┘
       ▲                                      │ 可选
       │         公网不可达时                  ▼
       └────────── frp / OpenFrp 隧道 ─── 仅转发 TCP/WS
                    （无游戏状态）
```

## 快速开始（网页 UI）

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

### 本机双浏览器打完一局井字棋

**终端 — 启动主机：**

```bash
python -m boardgame_platform host --port 8765
```

默认会尝试打开浏览器访问 `http://127.0.0.1:8765/`。  
若不想自动打开，加 `--no-browser`。

**浏览器标签页 1（房主）：**

1. 首页选择 **井字棋**
2. 填写昵称 → 点绿色 **创建房间**
3. 记下大号**房间号**，点 **准备**
4. 等另一人准备后，点 **开始游戏**
5. 用鼠标点击 3×3 棋盘落子

**浏览器标签页 2（加入方）：**

1. 同样打开 `http://127.0.0.1:8765/` → 井字棋
2. 填写昵称，输入房间号 → **进入房间**
3. **准备** → 等待开始 → 鼠标落子

首页还会显示若干灰色「即将推出」占位卡。

### 终端客户端（高级选项）

协议不变，仍可用终端 UI：

```bash
# 终端 1 已启动 host 后
python -m boardgame_platform client -n Alice   # 创建房间 → ready → start
python -m boardgame_platform client -n Bob     # 加入房间码 → ready → 输入 0-8
```

棋盘示意（终端空位显示编号；网页直接点击）：

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
   - `BoardGameHost.exe` — 建房者运行（开主机 + 网页 UI）
   - `BoardGameClient.exe` — 终端客户端（可选）

本机流程（局域网先测）：

1. 建房者双击 `BoardGameHost.exe`（默认端口 8765，窗口别关；会打开浏览器）
2. 两人用浏览器打开主机打印的网页地址，一人创建房间、一人输入房间码加入

异地：主机仍要配合 frp（见 `docs/frp-zh.md`），好友浏览器访问穿透后的 `http://公网host:port/`。

也可在已装 Python 的 Windows 上手动打包：

```powershell
.\packaging\build_windows.ps1
```

产物在 `dist\`（Host exe 已打包 `boardgame_platform/web` 静态资源）。

### 远程联机（frp）

详见 **[docs/frp-zh.md](docs/frp-zh.md)**（OpenFrp + 自建 frps）。

简要步骤：

1. 房主启动 `python -m boardgame_platform host`
2. 用 OpenFrp / frpc 把本机 `8765` 映射到公网
3. 浏览器创建房间拿到房间码
4. 分享：`http://公网host:port/` + 房间码
5. 好友用浏览器打开该地址并加入；或终端：  
   `python -m boardgame_platform client --host <公网> --port <映射端口> -n 昵称`

示例配置：`deploy/frpc.toml.example`。

## CLI

```bash
python -m boardgame_platform host [--host 0.0.0.0] [--port 8765] [--no-browser]
python -m boardgame_platform client [--url ws://127.0.0.1:8765/ws] [-n 昵称]
python -m boardgame_platform client --host 1.2.3.4 --port 18765 -n 小明
```

也可安装后使用入口脚本：`boardgame-host` / `boardgame-client`。

## 协议概要（JSON over WebSocket）

客户端 → 主机：`create_room` / `join_room` / `ready` / `start` / `move` / `leave` / `list_games` / `ping`

主机 → 客户端：`welcome` / `room_created` / `room_joined` / `room_update` / `game_started` / `state` / `game_over` / `error` / `pong` / `games`

井字棋走子：`{"type":"move","move":{"cell":0-8}}`。

`state` 经 `GamePlugin.view(for_player=...)` **按玩家过滤**后下发（井字棋为公开信息，接口仍统一）。

HTTP 辅助：`GET /` 网页、`GET /static/*` 资源、`GET /api/games`、`GET /health`、`WS /ws`。

## 如何新增一款游戏

1. 在 `boardgame_platform/games/` 新建模块，实现 `GamePlugin`：
   - `setup` / `validate` / `apply` / `view` / `is_over`
   - 设置 `game_id`、`display_name`、`min_players`、`max_players`
2. 使用 `@register_game` 装饰器注册
3. 在 `game_api.ensure_builtin_games_loaded()` 中 import 该模块
4. 客户端创建房间时指定 `game_id`（网页首页会列出已注册游戏）

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
│   ├── host.py              # FastAPI + WebSocket + 静态网页
│   ├── client.py            # 终端客户端（高级）
│   ├── room.py              # 房间码与大厅
│   ├── protocol.py          # 消息类型
│   ├── game_api.py          # 游戏插件接口与注册表
│   ├── games/
│   │   └── tictactoe.py     # 可玩演示
│   └── web/                 # 浏览器 UI（HTML/CSS/JS）
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── packaging/               # Windows PyInstaller（含 --add-data web）
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
