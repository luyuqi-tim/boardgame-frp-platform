# 使用 frp / OpenFrp 远程联机指南

本平台采用 **Listen-Server** 架构：房间创建者在自己的 PC 上运行权威主机，游戏逻辑全部在主机进程内执行。**frp 只负责打通网络**，绝不托管对局状态。

## 架构示意

```
好友客户端 ──WebSocket──► 公网入口 (frps / OpenFrp)
                              │
                              │ frp 隧道
                              ▼
                     房主 PC: boardgame host (:8765)
                              │
                              ▼
                        权威游戏逻辑 / 房间码
```

## 方案 A：OpenFrp（国内常用，免自建服务器）

1. 注册并登录 [OpenFrp](https://www.openfrp.net/)（或同类内网穿透服务）。
2. 在控制台创建一条 **TCP** 隧道：
   - 本地 IP：`127.0.0.1`
   - 本地端口：`8765`（与 host 默认端口一致）
   - 记录分配到的 **公网节点域名/IP** 与 **远程端口**
3. 在房主电脑启动 OpenFrp 客户端并启动该隧道。
4. 房主启动游戏主机：
   ```bash
   python -m boardgame_platform host --port 8765
   ```
5. 任一客户端（含房主自己）连接并创建房间，获得 **6 位房间码**。
6. 把下面信息发给好友：
   - WebSocket 地址：`ws://节点地址:远程端口/ws`
   - 房间码：例如 `A3K9XZ`
7. 好友运行：
   ```bash
   python -m boardgame_platform client --host 节点地址 --port 远程端口 -n 昵称
   ```
   选择「加入房间」并输入房间码。

> 注意：部分免费节点可能限制长时间连接或带宽，对局流量很小，一般足够。请遵守服务商条款。

## 方案 B：自建 frps + frpc

适合已有公网 VPS 的用户。

### 1. 服务器（有公网 IP）安装 frps

示例 `frps.toml`：

```toml
bindPort = 7000
auth.method = "token"
auth.token = "换成强随机串"
```

启动：

```bash
frps -c frps.toml
```

防火墙放行 `7000`（控制）以及你打算映射的业务端口（如 `18765`）。

### 2. 房主电脑配置 frpc

复制本仓库 `deploy/frpc.toml.example` 为 `frpc.toml`，填写：

- `serverAddr` / `serverPort`：你的 VPS
- `auth.token`：与 frps 一致
- `localPort = 8765`
- `remotePort = 18765`（示例）

启动：

```bash
frpc -c frpc.toml
```

### 3. 开房间与分享

```bash
# 房主
python -m boardgame_platform host --port 8765

# 本地或远程客户端
python -m boardgame_platform client --host <VPS公网IP> --port 18765 -n 小明
```

创建房间后分享：**`ws://VPS:18765/ws` + 房间码**。

## 安全建议

- Token 不要提交到 Git；`.gitignore` 已忽略本地 `frpc.toml`。
- 仅在对局期间开启隧道，打完可关掉。
- 本平台无账号系统，房间码相当于弱口令；勿在公共场合长期挂机。
- 游戏逻辑只在房主进程，**不要把业务部署到 frps**。

## 故障排查

| 现象 | 排查 |
|------|------|
| 客户端连不上 | 隧道是否在线；端口是否一致；本机 host 是否在听 `0.0.0.0:8765` |
| 连上但进房失败 | 房间码大小写（服务端会规范化）；是否已开始对局；房间是否已满 |
| WebSocket 握手失败 | 确认 URL 路径为 `/ws`；勿漏写 `ws://` |
| OpenFrp 节点慢 | 换节点或改用自建 frps |

## 与局域网测试的关系

同一台机器两个终端（或局域网直连）**不需要 frp**，直接：

```bash
python -m boardgame_platform host
python -m boardgame_platform client -n Alice
python -m boardgame_platform client -n Bob
```

frp 只在「不在同一局域网、需要公网可达」时使用。
