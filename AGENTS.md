# MOPS — Multi-node Outbound Proxy System

## 系统架构

```
App → Client(:10081) → mDNS发现 → Server(:10080) → 公网
                                    ↓
                              mDNS 广播 (TTL=60s)
```

### 核心组件 (src/mops/)

| 模块 | 职责 |
|------|------|
| `protocol.py` | 共享常量：端口、TTL、熔断阈值 |
| `stats.py` | 流量统计 (per-node 上传/下载) |
| `tunnel.py` | 双向异步流量拷贝 |
| `server.py` | TCP 透传 + mDNS 广播 |
| `discovery.py` | mDNS 服务浏览 (Client 用) |
| `scheduler.py` | 负载均衡 + 节点池 + 熔断 |
| `client.py` | SOCKS5 + HTTP CONNECT 代理 |
| `api.py` | aiohttp REST API (GET /status) |
| `service.py` | 系统服务管理 (systemd/sc) |
| `proxy.py` | 系统代理配置 (纯函数) |
| `__main__.py` | CLI 入口 (argparse) |

### 隧道协议

Client 连接 Server TCP 端口后发送 `host:port\n`，Server 解析后连接真实目标，双向字节流转发。

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

## 开发约定

- 依赖管理：`uv sync` / `uv add`
- 测试：`uv run pytest tests/ -v --cov=mops`
- 打包：`uv run python build.py` (Nuitka)
- Python 3.12+, asyncio 原生协程，禁止多线程/多进程
- 测试覆盖率：90% (164 个测试)，目标 ≥85%
- 服务模式：`--service` 标志启用（隐藏），无交互式输出，适合 systemd/sc 后台运行

## 目录结构

```
MOPS/
├── src/mops/           # 源码
│   ├── __main__.py     # CLI 入口
│   ├── protocol.py     # 共享常量
│   ├── stats.py        # 流量统计
│   ├── tunnel.py       # 双向流量拷贝
│   ├── server.py       # TCP 透传 + mDNS
│   ├── client.py       # SOCKS5 + HTTP CONNECT
│   ├── discovery.py    # mDNS 服务浏览
│   ├── scheduler.py    # 负载均衡 + 熔断
│   ├── api.py          # REST API
│   ├── service.py      # 系统服务管理
│   └── proxy.py        # 系统代理配置
├── tests/              # 测试 (164 个)
├── pyproject.toml      # 项目配置 (hatchling)
├── build.py            # Nuitka 打包脚本
└── README.md           # 文档
```
