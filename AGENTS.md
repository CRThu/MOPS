# MOPS — Multi-node Outbound Proxy System

## 系统架构

```
App → Client(:10081) → mDNS发现 → Server(:10080) → 公网
                                    ↓
                              mDNS 广播 (TTL=60s)
                                    ↓
                              API(:10082) → Dashboard (G6 拓扑图)
```

### 核心组件 (src/mops/)

| 模块 | 职责 |
|------|------|
| `protocol.py` | 共享常量：端口、TTL、熔断阈值 |
| `stats.py` | 流量统计 (per-node 上传/下载) + ConnectionTracker (连接追踪) |
| `tunnel.py` | 双向异步流量拷贝 |
| `server.py` | TCP 透传 + mDNS 广播 + 连接生命周期记录 |
| `discovery.py` | mDNS 服务浏览 (Client 用) |
| `scheduler.py` | 负载均衡 + 节点池 + 熔断 |
| `client.py` | SOCKS5 + HTTP CONNECT 代理 |
| `api.py` | aiohttp REST API + 静态文件服务 |
| `service.py` | 系统服务管理 (systemd/sc) |
| `proxy.py` | 系统代理配置 (纯函数) |
| `__main__.py` | CLI 入口 (argparse) |

### 隧道协议

Client 连接 Server TCP 端口后发送 `host:port\n`，Server 解析后连接真实目标，双向字节流转发。

### 连接追踪 (ConnectionTracker)

Server 端记录每个 client 连接的生命周期：
- `start(client_ip, target_host, target_port)` → 返回 conn_id
- `end(conn_id)` → 标记完成，移入 completed 队列
- 滚动窗口：保留最近 5 分钟的已完成连接
- 线程安全：`threading.Lock` 保护并发访问
- API 返回：`/api/server` 的 `connections` 字段包含 active + completed 连接

### 负载均衡

- `random`（默认）：随机选择，流量均匀
- `hash`：`hash(client_ip:target_host)` 会话保持

### 健康检查

- mDNS TTL=60s：Server 挂掉 60 秒内 Client 感知
- 被动熔断：`fails >= 2` → 观察池，30 秒自动恢复

### 实现注意事项

- **zeroconf 异步 API**: Server 运行在 asyncio event loop 中，必须使用 `async_register_service` / `async_unregister_service`，不能用同步的 `register_service`（会在已有 loop 上下文中抛 `EventLoopBlocked`）
- **src 布局**: 源码位于 `src/mops/`，通过 `pyproject.toml` 配置，支持 PyPI 发布
- **mDNS IP 检测**: 默认通过 UDP 连 `8.8.8.8` 获取路由表实际出口网卡 IP；`--bind` 可手动覆盖
- **前端构建**: Dashboard 使用 AntV G6 5.x + Vite 8 + TypeScript，构建输出到 `src/mops/static/`
- **拓扑图**: `App → Client(按 client_ip 区分) → Server(按发现的节点) → Internet`，颜色区分节点类型和在线状态，橙色实线表示 active 数据流

## CLI 结构

```
mops run [server|client|both] [--port 10080] [--bind <ip>]  # 前台运行
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
| `GET /static/*` | 前端构建产物 |

> `/api/client` 已移除。所有信息通过 `/api/server` 获取。

## 开发约定

- Python 依赖管理：`uv sync` / `uv add`
- 前端依赖管理：`bun install`（在 web/ 目录）
- Python 测试：`uv run pytest tests/ -v --cov=mops`
- 前端单元测试：`cd web && bun run test`（Vitest）
- 前端渲染测试：`cd web && bun run test:e2e`（Playwright）
- 前端构建：`cd web && bun run build`（输出到 src/mops/static/）
- 打包：`uv run python build.py` (Nuitka)
- Python 3.12+, asyncio 原生协程，禁止多线程/多进程
- Python 测试覆盖率：88% (181 个测试)，目标 ≥85%
- CI/CD：`.github/workflows/ci.yml`（Python 测试 + Vitest + Playwright + 构建验证）
- 服务模式：`--service` 标志启用（隐藏），无交互式输出，适合 systemd/sc 后台运行

## 目录结构

```
MOPS/
├── src/mops/           # Python 源码
│   ├── __main__.py     # CLI 入口
│   ├── protocol.py     # 共享常量
│   ├── stats.py        # 流量统计 + ConnectionTracker
│   ├── tunnel.py       # 双向流量拷贝
│   ├── server.py       # TCP 透传 + mDNS + 连接追踪
│   ├── client.py       # SOCKS5 + HTTP CONNECT
│   ├── discovery.py    # mDNS 服务浏览
│   ├── scheduler.py    # 负载均衡 + 熔断
│   ├── api.py          # REST API + 静态文件服务
│   ├── static/         # Vite 构建输出（G6 Dashboard）
│   ├── service.py      # 系统服务管理
│   └── proxy.py        # 系统代理配置
├── web/                # 前端源码（Bun + Vite 8 + TS + G6）
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── playwright.config.ts
│   ├── index.html
│   ├── e2e/            # Playwright 渲染测试
│   └── src/
│       ├── main.ts     # 数据轮询 + 转换
│       ├── graph.ts    # G6 拓扑图模块 (Canvas renderer)
│       ├── style.css   # 暗色主题
│       ├── format.test.ts    # 格式化函数测试 (11)
│       ├── toTopo.test.ts    # 数据转换测试 (11)
│       └── graph.test.ts     # Graph 模块测试 (7)
├── tests/              # 测试 (181 个, 88% 覆盖率)
├── .github/workflows/ci.yml  # CI/CD 流水线
├── pyproject.toml      # 项目配置 (hatchling)
├── build.py            # Nuitka 打包脚本
└── README.md           # 文档
```
