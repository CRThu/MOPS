# MOPS

多节点出口代理系统 — 轻量级分布式出口负载均衡系统。

通过局域网内多台设备的 IP 聚合，绕过网关单 IP 限速。

## 功能特性

- **多协议支持** — 同一端口自动识别 SOCKS5 / HTTP CONNECT / HTTP 代理（GET/POST），类似 Clash
- **零配置发现** — 基于 mDNS，Server 广播、Client 自动发现，无需手动配置节点列表
- **负载均衡** — `random`（随机）/ `hash`（会话保持）两种策略
- **健康检查** — mDNS TTL 60s + 被动熔断（连续失败自动隔离，30s 后恢复）
- **连接追踪** — Server 端记录所有 client 连接（IP、目标、状态），最近 5 分钟滚动历史
- **系统代理** — 一键设置/取消系统全局代理（Windows / macOS / Linux）
- **REST API** — 实时查看节点状态、流量统计、连接信息
- **Web Dashboard** — AntV G6 拓扑图 + 暗色科技感界面，15s 自动刷新

## 快速开始

```bash
# 安装 Python 依赖
uv sync

# 安装前端依赖（可选，仅开发 Dashboard 时需要）
cd web && bun install && bun run build && cd ..

# 出口机启动 Server（对外暴露出口）
uv run python -m mops run server

# 主力机启动 Client（本机代理入口）
uv run python -m mops run client

# 或者混合模式（同时跑 Server + Client）
uv run python -m mops run both
```

Client 启动后，默认监听 `127.0.0.1:10081`，自动发现局域网内的 Server 节点。

## CLI 参考

```bash
mops                                              # 默认 both 模式启动
mops run        [server|client|both] [--port 10080] [--strategy random|hash] [--listen 127.0.0.1] [--weight 1] [--bind <ip>]
mops service install                              # 注册服务（无运行时参数）
mops service start   [--mode both] [--port 10080] [--strategy random] [--bind <ip>]
mops service stop                                  # 停止服务
mops service status                                # 查看服务状态
mops service uninstall                             # 卸载服务
mops service log    [-n 50] [-s keyword]           # 查看日志
mops proxy on     [--port 10081]                   # 设置系统全局代理
mops proxy off                                     # 取消系统全局代理
mops proxy status                                  # 查看代理状态
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--port` | 基础端口，所有端口从此衍生 | `10080` |
| `--strategy` | 负载均衡策略: `random` 或 `hash` | `random` |
| `--weight` | Server 权重 (仅 server 模式) | `1` |
| `--listen` | Client 监听地址 | `127.0.0.1` |
| `--bind` | mDNS 广播的 IP 地址（通过路由表自动检测） | `auto` |
| `--mode` | 运行模式: `server` / `client` / `both` | `both` |

### 端口分配

| 组件 | 端口 |
|------|------|
| Server TCP | `base_port` (默认 10080) |
| Client 代理 | `base_port + 1` (默认 10081) |
| REST API | `base_port + 2` (默认 10082) |

## 代理协议

同一端口，自动识别协议类型，无需手动配置：

| 协议 | 客户端请求 | 用途 |
|------|------------|------|
| **SOCKS5** | `0x05 0x01 0x00` 握手 | TCP 代理（HTTP/HTTPS/任意 TCP） |
| **HTTP CONNECT** | `CONNECT host:port HTTP/1.1` | HTTPS 隧道 |
| **HTTP 代理** | `GET http://host/path HTTP/1.1` | 普通 HTTP 代理（GET/POST 等） |

## 使用示例

### curl 测试

```bash
# SOCKS5 代理
curl.exe -x socks5://127.0.0.1:10081 ifconfig.me

# HTTP 代理（支持 HTTP 和 HTTPS）
curl.exe -x http://127.0.0.1:10081 ifconfig.me
curl.exe -x http://127.0.0.1:10081 https://ifconfig.me

# 不走代理（直连对比）
curl.exe ifconfig.me
```

> **提示**: Windows 上如果系统已配置代理（如 Clash 在 `127.0.0.1:7890`），测试时需加 `--noproxy "*"` 绕过。

### 设置系统代理

```bash
# 开启系统全局代理（所有应用流量走 MOPS）
mops proxy on

# 关闭并恢复原设置
mops proxy off

# 查看当前代理状态
mops proxy status
```

### Clash / Clash Verge 配置

1. 在 Clash Verge 中，选中订阅节点 → 点「编辑」，添加以下内容：

```yaml
prepend:
  - type: 'socks5'
    name: 'SOCKS5 127.0.0.1:10081'
    server: '127.0.0.1'
    port: 10081
```

2. 保存后，在代理页面右上角「链式代理」中选择 `SOCKS5 127.0.0.1:10081` 节点

> **说明**: `prepend` 会在订阅节点前插入 MOPS 节点，通过链式代理让流量先走 MOPS，再走原有代理节点。

### Web Dashboard

启动服务后，浏览器访问 `http://127.0.0.1:10082/` 查看可视化面板：

- AntV G6 5.x 拓扑图，dagre 从左到右布局（App → Client → Server → Internet）
- 活跃连接橙色流动动画，15 秒自动刷新
- 右侧 Connections 面板：实时显示所有连接状态
- 底部 Server Traffic 表格：各节点上下行流量

### REST API

| 端点 | 说明 |
|------|------|
| `GET /` | Web Dashboard 页面 |
| `GET /api/server` | Server 状态 + 流量 + 连接信息 JSON |

<details>
<summary>响应示例</summary>

```json
{
  "nodes": [
    {
      "ip": "192.168.1.100",
      "port": 10080,
      "fails": 0,
      "up": 1024000,
      "down": 5120000
    }
  ],
  "total_up": 1024000,
  "total_down": 5120000,
  "active_conns": 3,
  "connections": [
    {
      "conn_id": "1",
      "client_ip": "192.168.1.50",
      "target_host": "example.com",
      "target_port": 443,
      "status": "active",
      "started_at": 12345.6
    },
    {
      "conn_id": "2",
      "client_ip": "192.168.1.50",
      "target_host": "google.com",
      "target_port": 443,
      "status": "completed",
      "started_at": 12300.0,
      "ended_at": 12340.0
    }
  ],
  "uptime": 3600
}
```

</details>

> **注意**: `/api/client` 已移除。Client 端不再提供独立 API，所有信息通过 Server 的 `/api/server` 获取。

## 负载均衡

| 策略 | 说明 |
|------|------|
| `random` | 随机选择节点，流量最均匀 |
| `hash` | 按 `client_ip:target_host` 哈希，会话保持 |

## 健康检查

- **mDNS 广播** — Server 每 60 秒刷新 TTL，Client 自动感知节点加入/离开
- **被动熔断** — 连续 2 次连接失败 → 节点移入观察池，30 秒后自动恢复

## 系统服务

### Linux (systemd)

```bash
uv run python -m mops service install
uv run python -m mops service start --mode both --port 10080 --bind 192.168.1.100
uv run python -m mops service status
uv run python -m mops service stop
uv run python -m mops service uninstall
```

### Windows (sc)

```powershell
uv run python -m mops service install
uv run python -m mops service start --mode both --port 10080 --bind 192.168.1.100
uv run python -m mops service status
uv run python -m mops service stop
uv run python -m mops service uninstall
```

## 日志

日志自动保存到 `~/.mops/logs/mops.log`（10MB 轮转，保留 7 天）：

```bash
mops service log                # 最近 50 行
mops service log -n 100         # 最近 100 行
mops service log -s "error"     # 搜索关键词
```

## 开发

```bash
# Python
uv sync --extra dev
uv run pytest tests/ -v --cov=mops
uv run python build.py          # Nuitka 打包

# 前端 Dashboard
cd web
bun install                     # 安装依赖（Bun）
bun run dev                     # 开发模式（热更新）
bun run build                   # 构建到 src/mops/static/
```

### 项目结构

```
MOPS/
├── src/mops/
│   ├── __init__.py       # 版本号
│   ├── __main__.py       # CLI 入口
│   ├── protocol.py       # 共享常量 + 日志路径
│   ├── stats.py          # 流量统计 + ConnectionTracker
│   ├── tunnel.py         # 双向流量拷贝
│   ├── server.py         # TCP 透传 + mDNS + 连接追踪
│   ├── client.py         # SOCKS5 + HTTP CONNECT + HTTP 代理
│   ├── discovery.py      # mDNS 服务浏览
│   ├── scheduler.py      # 负载均衡 + 熔断
│   ├── api.py            # REST API + 静态文件服务
│   ├── dashboard.html    # Legacy Dashboard 模板（备用）
│   ├── static/           # Vite 构建输出（G6 Dashboard）
│   │   ├── index.html
│   │   ├── dashboard.js
│   │   └── dashboard.css
│   ├── service.py        # 系统服务管理
│   └── proxy.py          # 系统代理配置
├── web/                  # 前端源码（Bun + Vite + TS + G6）
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.ts       # 数据轮询 + 转换 + 渲染
│       ├── graph.ts      # G6 拓扑图模块
│       └── style.css     # 暗色主题样式
├── tests/                # 181 个测试，88% 覆盖率
├── build.py              # Nuitka 打包脚本
├── pyproject.toml        # 项目配置 (hatchling)
├── .gitignore
└── LICENSE               # Apache License 2.0
```

## 许可证

[Apache License 2.0](LICENSE)
