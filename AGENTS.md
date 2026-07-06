# MOPS — Multi-node Outbound Proxy System

## 系统架构

```
App → Client(:10081) → mDNS发现 → Server(:10080) → 公网
                                    ↓
                              mDNS 广播 (TTL=60s)
                                    ↓
                              API(:10082) → Dashboard (G6 拓扑图)

mops dashboard → mDNS发现 → 查询各 Server /api/server → 聚合 → 前端展示
```

### 核心组件 (src/mops/)

| 模块 | 职责 |
|------|------|
| `protocol.py` | 共享常量：端口、TTL、熔断阈值、NODE_HISTORY_TTL、SPEED_WINDOW |
| `stats.py` | 流量统计 + ConnectionTracker + NodeRegistry（离线节点保留）+ TrafficHistory（实时速率） |
| `tunnel.py` | 双向异步流量拷贝 |
| `server.py` | TCP 透传 + mDNS 广播（含 api_port 属性）+ 连接生命周期记录 |
| `discovery.py` | mDNS 服务浏览（Client + Dashboard 用，解析 api_port/hostname） |
| `scheduler.py` | 负载均衡 + 节点池 + 熔断（NodeInfo 含 api_port/hostname） |
| `client.py` | SOCKS5 + HTTP CONNECT 代理 |
| `dashboard.py` | 独立 Dashboard 服务：mDNS 发现 → 查询各 Server API → 聚合 → Web 服务 |
| `api.py` | aiohttp REST API + 静态文件服务（/api/server + /api/dashboard 别名） |
| `service.py` | 系统服务管理 (systemd/sc) |
| `proxy.py` | 系统代理配置 (纯函数) |
| `__main__.py` | CLI 入口 (argparse)，含 `dashboard` 子命令 |

### 隧道协议

Client 连接 Server TCP 端口后发送 `host:port\n`，Server 解析后连接真实目标，双向字节流转发。

### 连接追踪 (ConnectionTracker)

Server 端记录每个 client 连接的生命周期：
- `start(client_ip, target_host, target_port)` → 返回 conn_id
- `end(conn_id)` → 标记完成，移入 completed 队列
- 滚动窗口：保留最近 5 分钟的已完成连接
- 线程安全：`threading.Lock` 保护并发访问
- API 返回：`/api/server` 的 `connections` 字段包含 active + completed 连接

### 节点注册表 (NodeRegistry)

Dashboard 使用 NodeRegistry 跟踪所有发现的节点：
- `record_seen(ip, port, api_port, hostname)` → 记录/更新节点
- `mark_offline(ip, port)` → 标记离线（不立即删除）
- `prune()` → 清理超过 NODE_HISTORY_TTL（1小时）的离线节点
- 线程安全：`threading.Lock` 保护并发访问

### 实时速率 (TrafficHistory)

基于滑动窗口计算实时速率：
- 保留最近 SPEED_WINDOW（5）个采样点
- `record(total_up, total_down, active_conns)` → 记录快照
- `compute_speed()` → 返回 (speed_up, speed_down) bytes/s

### 负载均衡

- `random`（默认）：随机选择，流量均匀
- `hash`：`hash(client_ip:target_host)` 会话保持

### 健康检查

- mDNS TTL=60s：Server 挂掉 60 秒内 Client 感知
- 被动熔断：`fails >= 2` → 观察池，30 秒自动恢复

### 实现注意事项

- **zeroconf 异步 API**: Server 运行在 asyncio event loop 中，必须使用 `async_register_service` / `async_unregister_service`
- **src 布局**: 源码位于 `src/mops/`，通过 `pyproject.toml` 配置
- **mDNS IP 检测**: 默认通过 UDP 连 `8.8.8.8` 获取路由表实际出口网卡 IP；`--bind` 可手动覆盖
- **mDNS 属性**: Server 广播 `api_port` 属性，Client/Dashboard 解析用于 API 查询
- **前端构建**: Dashboard 使用 AntV G6 5.x + Vite 8 + TypeScript，构建输出到 `src/mops/static/`
- **拓扑图**: `App → Client(本地) → Server×N → Internet`，语义缩放（远看隐藏标签），活跃边流动粒子动画
- **Dashboard 独立运行**: `mops dashboard` 通过 mDNS 发现 Server，主动查询各 Server API，聚合后返回前端

## CLI 结构

```
mops run [server|client|both] [--port 10080] [--bind <ip>]  # 前台运行
mops dashboard [--port 10082]                               # 独立 Dashboard
mops service install                           # 注册服务（无运行时参数）
mops service start [--mode both] [--port 10080] [--strategy random] [--bind <ip>]
mops service uninstall/stop/status/log         # 其他服务管理
mops proxy on/off/status                       # 系统代理
```

### mDNS IP 检测

- 默认通过 UDP 连 `8.8.8.8` 获取路由表实际出口网卡 IP
- `--bind` 可手动覆盖（适用于多网卡或容器环境）

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /` | Web Dashboard（优先返回 static/index.html，回退 dashboard.html） |
| `GET /api/server` | Server 状态 + 流量 + 连接信息 |
| `GET /api/dashboard` | Dashboard 聚合状态（/api/server 别名） |
| `GET /static/*` | 前端构建产物 |

## 开发约定

- Python 依赖管理：`uv sync` / `uv add`
- 前端依赖管理：`bun install`（在 web/ 目录）
- Python 测试：`uv run pytest tests/ -v --cov=mops`
- 前端单元测试：`cd web && bun run test`（Vitest）
- 前端渲染测试：`cd web && bun run test:e2e`（Playwright）
- 前端构建：`cd web && bun run build`（输出到 src/mops/static/）
- 打包：`uv run python build.py` (Nuitka)
- Python 3.12+, asyncio 原生协程，禁止多线程/多进程
- Python 测试覆盖率：202 个测试，目标 ≥85%
- CI/CD：`.github/workflows/ci.yml`（Python 测试 + Vitest + Playwright + 构建验证）
- 服务模式：`--service` 标志启用（隐藏），无交互式输出，适合 systemd/sc 后台运行

## 目录结构

```
MOPS/
├── src/mops/           # Python 源码
│   ├── __main__.py     # CLI 入口
│   ├── protocol.py     # 共享常量
│   ├── stats.py        # 流量统计 + ConnectionTracker + NodeRegistry + TrafficHistory
│   ├── tunnel.py       # 双向流量拷贝
│   ├── server.py       # TCP 透传 + mDNS + 连接追踪
│   ├── client.py       # SOCKS5 + HTTP CONNECT
│   ├── discovery.py    # mDNS 服务浏览（含 registry 集成）
│   ├── scheduler.py    # 负载均衡 + 熔断
│   ├── dashboard.py    # 独立 Dashboard 服务
│   ├── api.py          # REST API + 静态文件服务
│   ├── static/         # Vite 构建输出（G6 Dashboard）
│   ├── service.py      # 系统服务管理
│   └── proxy.py        # 系统代理配置
├── web/                # 前端源码（Bun + Vite 8 + TS + G6）
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── playwright.config.ts
│   ├── index.html      # 双栏布局 (70/30)
│   ├── e2e/            # Playwright 渲染测试
│   └── src/
│       ├── main.ts     # 入口：1s 轮询 /api/dashboard
│       ├── types.ts    # TypeScript 接口
│       ├── format.ts   # 格式化函数
│       ├── data.ts     # API 获取 + toTopo 转换
│       ├── topo.ts     # G6 拓扑图（语义缩放 + 流动粒子）
│       ├── cards.ts    # 服务器状态卡片
│       ├── style.css   # 工业暗色主题
│       ├── format.test.ts   # 格式化测试 (11)
│       ├── toTopo.test.ts   # 数据转换测试 (7)
│       └── graph.test.ts    # Graph 模块测试 (7)
├── tests/              # 测试 (202 个)
├── .github/workflows/ci.yml  # CI/CD 流水线
├── pyproject.toml      # 项目配置 (hatchling)
├── build.py            # Nuitka 打包脚本
└── README.md           # 文档
```
