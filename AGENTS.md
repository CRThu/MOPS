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
| `protocol.py` | 共享常量 + NodeInfo dataclass + 隧道头构建/解析 (`build_header`, `parse_header`) |
| `stats/traffic.py` | 流量统计（每个节点的上行/下行字节数） |
| `stats/connection.py` | 连接生命周期追踪（active + completed 滚动窗口） |
| `stats/registry.py` | 节点注册表（mDNS 发现的节点，含离线保留） |
| `stats/history.py` | 实时速率计算（滑动窗口） |
| `tunnel.py` | 双向异步流量拷贝 |
| `server.py` | TCP 透传 + mDNS 广播（含 api_port 属性）+ 连接生命周期记录 |
| `discovery.py` | mDNS 服务浏览（Client + Dashboard 用，解析 api_port/hostname） |
| `scheduler.py` | 负载均衡 + 节点池 + 熔断 |
| `client.py` | SOCKS5 + HTTP CONNECT 代理 |
| `dashboard.py` | 独立 Dashboard 服务：mDNS 发现 → 查询各 Server API → 聚合 → Web 服务 |
| `api.py` | aiohttp REST API + 统一 /api/dashboard 响应 |
| `web.py` | 共享静态文件服务（api.py + dashboard.py 共用） |
| `service.py` | 系统服务管理 (systemd/sc) |
| `proxy.py` | 系统代理配置 (纯函数) |
| `__main__.py` | CLI 入口 (argparse)，含 `dashboard` 子命令 |

### 隧道协议

Client 连接 Server TCP 端口后发送一行 JSON header，Server 解析后连接真实目标，双向字节流转发。

**Header 格式（v1）：**
```json
{"version":1,"host":"example.com:443","client_port":10090,"client_host":"Carrot-PC"}
```

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `version` | int | 是 | 协议版本，当前固定为 `1` |
| `host` | string | 是 | 目标地址，格式 `host:port` |
| `client_port` | int | 否 | Client 监听端口，用于区分同 IP 上的多个实例 |
| `client_host` | string | 否 | Client 机器 hostname，用于 Dashboard 显示 |

- `build_header(host, port, client_port, client_host)` → bytes（含 `\n`）
- `parse_header(raw)` → `(host, port, client_port, client_host)`
- Server 只 `readline()` 一次，之后全部 raw TCP 透传

### 连接追踪 (ConnectionTracker)

Server 端记录每个 client 连接的生命周期：
- `start(client_ip, target_host, target_port, client_port, client_host)` → 返回 conn_id
- `end(conn_id)` → 标记完成，移入 completed 队列
- `active_count()` → 返回当前活跃连接数
- `get_connections()` → 返回所有 active + completed 连接列表
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
- **mDNS IP 检测**: 默认通过 UDP 连 `8.8.8.8` 获取路由表实际出口网卡 IP；`--advertise` 可手动覆盖
- **mDNS 属性**: Server 广播 `api_port` 属性，Client/Dashboard 解析用于 API 查询
- **前端构建**: Dashboard 使用 AntV G6 5.x + Vite 8 + TypeScript，构建输出到 `src/mops/static/`
- **拓扑图**: `App → Client(本地) → Server×N → Internet`，语义缩放（远看隐藏标签），活跃边流动虚线动画
- **Dashboard 独立运行**: `mops dashboard` 通过 mDNS 发现 Server，主动查询各 Server API，聚合后返回前端

## CLI 结构

```
mops run [options]                                  # 前台运行
  --mode {server,client,both}                       # 运行模式（默认 both）
  --server-port INT                                 # Server TCP 端口（默认 10080）
  --client-port INT                                 # Client 代理端口（默认 10081）
  --api-port INT                                    # REST API 端口（默认 10082）
  --listen HOST                                     # Client 监听地址（默认 127.0.0.1）
  --advertise HOST                                  # mDNS 广播地址（默认自动检测）
  --strategy {random,hash}                          # 负载均衡策略（默认 random）
  --weight INT                                      # Server 权重（默认 1）
  -c, --config PATH                                 # 从配置文件加载参数

mops dashboard [--port 10100]                          # 独立 Dashboard
mops service install                                # 注册服务
mops service start [同 run 的参数] [-c config.json]   # 启动服务
mops service uninstall/stop/status/log [-n 50] [-s keyword] # 其他服务管理
mops proxy on [--port 10081]                        # 设置系统代理
mops proxy off/status                               # 取消/查看代理
```

### mDNS IP 检测

- 默认通过 UDP 连 `8.8.8.8` 获取路由表实际出口网卡 IP
- `--advertise` 可手动覆盖（适用于多网卡或容器环境）

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /` | Web Dashboard（优先返回 static/index.html，回退提示构建） |
| `GET /api/server` | Server 状态 + 流量 + 连接信息 |
| `GET /api/dashboard` | Dashboard 聚合状态（/api/server 别名） |
| `GET /static/*` | 前端构建产物 |

## 后台启动方式（Windows）

```powershell
# uv 路径（按需替换）
$uv = "C:\Users\$env:USERNAME\.local\bin\uv.exe"
$logDir = $env:TEMP

# 推荐: cmd /c + WindowStyle Hidden（管道重定向在 cmd 内部完成，不阻塞）
# ⚠️ 禁止用 Start-Process -NoNewWindow + -RedirectStandardOutput/Err
#    PowerShell 的 Redirect 参数创建管道，子进程写满缓冲区后会阻塞

# Dashboard
Start-Process cmd -ArgumentList "/c","$uv run python -m mops dashboard --port 10100 >`"$logDir\mops-dash.log`" 2>&1" -WindowStyle Hidden

# 单实例（both 模式: server + client）
Start-Process cmd -ArgumentList "/c","$uv run python -m mops run --mode both --server-port 10080 --client-port 10090 --api-port 10082 --listen 127.0.0.1 >`"$logDir\mops-inst1.log`" 2>&1" -WindowStyle Hidden

# 多实例示例
Start-Process cmd -ArgumentList "/c","$uv run python -m mops run --mode both --server-port 20080 --client-port 20090 --api-port 20082 --listen 127.0.0.1 >`"$logDir\mops-inst2.log`" 2>&1" -WindowStyle Hidden
```

- `cmd /c "... >file 2>&1" -WindowStyle Hidden`：重定向在 cmd 内部完成，PowerShell 不持有管道，子进程不会阻塞
- `-WindowStyle Hidden` 隐藏窗口，不弹出 cmd 黑框
- 不要在进程运行时用 `Get-Content` 读日志文件（会阻塞），等进程退出后再读
- 每个实例需独立指定 server-port / client-port / api-port，避免端口冲突
- 验证启动：`netstat -aon | Select-String "1008"` 检查端口监听
- 查看日志：`Get-Content $env:TEMP\mops-*.log`
- 停止所有：`Get-Process python, uv | Stop-Process -Force`
- 不要用 `Start-Job` 运行长期外部进程——其 PowerShell 子进程退出时会杀子进程树

## 开发约定

- **版本管理**：必须使用 `uv run bump-my-version bump patch|minor|major` 升版本，禁止手动修改版本号
- Python 依赖管理：`uv sync` / `uv add`
- 前端依赖管理：`bun install`（在 web/ 目录）
- Python 测试：`uv run pytest tests/ -v --cov=mops`
- 前端单元测试：`cd web && bun run test`（Vitest）
- 前端渲染测试：`cd web && bun run test:e2e`（Playwright）
- 前端构建：`cd web && bun run build`（输出到 src/mops/static/）
- 打包：`uv run python build.py` (Nuitka)
- Python 3.12+, asyncio 原生协程，禁止多线程/多进程（ConnectionTracker/NodeRegistry 保留 threading.Lock 因为 zeroconf 回调在后台线程）
- Python 测试覆盖率：243 个测试，目标 ≥85%
- CI/CD：`.github/workflows/ci.yml`（Python 测试 + Vitest + Playwright + 构建验证）
- 服务模式：通过 `-c/--config` 传入配置文件，OS 服务启动时自动加载

## 目录结构

```
MOPS/
├── src/mops/           # Python 源码
│   ├── __main__.py     # CLI 入口
│   ├── protocol.py     # 共享常量 + NodeInfo dataclass + 隧道头构建/解析
│   ├── stats/          # 统计模块（按职责拆分）
│   │   ├── __init__.py # 重新导出（向后兼容）
│   │   ├── traffic.py  # TrafficStats（流量计数）
│   │   ├── connection.py # ConnectionTracker（连接追踪）
│   │   ├── registry.py # NodeRegistry（节点注册表）
│   │   └── history.py  # TrafficHistory（实时速率）
│   ├── tunnel.py       # 双向流量拷贝
│   ├── server.py       # TCP 透传 + mDNS + 连接追踪
│   ├── client.py       # SOCKS5 + HTTP CONNECT
│   ├── discovery.py    # mDNS 服务浏览（含 registry 集成）
│   ├── scheduler.py    # 负载均衡 + 熔断
│   ├── dashboard.py    # 独立 Dashboard 服务
│   ├── api.py          # REST API + 统一 /api/dashboard 响应
│   ├── web.py          # 共享静态文件服务
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
│       ├── topo.ts     # G6 拓扑图（语义缩放 + 流动虚线动画）
│       ├── graph.ts    # G6 拓扑图模块（替代实现）
│       ├── cards.ts    # 服务器状态卡片
│       ├── style.css   # 工业暗色主题
│       ├── format.test.ts   # 格式化测试 (11)
│       ├── toTopo.test.ts   # 数据转换测试 (16)
│       └── graph.test.ts    # Graph 模块测试 (10)
├── tests/              # 测试 (243 个)
├── .github/workflows/ci.yml  # CI/CD 流水线
├── pyproject.toml      # 项目配置 (hatchling)
├── build.py            # Nuitka 打包脚本
└── README.md           # 文档
```

## 组件独立性

Client、Server、Dashboard 三个组件互相独立，可以单独导入而不触发其他组件的加载：

```bash
# import server 不触发 client/dashboard
python -c "from mops.server import MopsServer"

# import client 不触发 server/dashboard
python -c "from mops.client import MopsClient"

# import dashboard 不触发 server/client
python -c "from mops.dashboard import MopsDashboard"
```

**禁止的依赖**：
- server ↔ client
- server ↔ dashboard
- client ↔ dashboard
- api → server/client（api 只接收 stats 对象）

**依赖方向**：
```
protocol.py  ←── server, client, dashboard, discovery, scheduler, tunnel, service, __main__
stats/*      ←── 各组件按需 import 需要的子模块
tunnel.py    ←── server.py, client.py
scheduler.py ←── client.py, dashboard.py, discovery.py
discovery.py ←── client.py, dashboard.py
proxy.py     ←── __main__.py（top-level）
server.py    ←── __main__.py（lazy）
client.py    ←── __main__.py（lazy）
dashboard.py ←── __main__.py（lazy）
api.py       ←── __main__.py（lazy）
```
