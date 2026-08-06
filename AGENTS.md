# MOPS — Multi-node Outbound Proxy System (Windows Go 版)

## 系统架构

```
App → Client SOCKS5(:10081) → mDNS 局域网自动发现 → Server(:10080) → 公网
                                     ↓
                             zeroconf 广播 (mDNS)
                                     ↓
                     Tailscale 风格终端 CLI (`mops status`)
```

### 核心组件 (`cmd/mops/` & `pkg/mops/`)

| 模块 | 职责 |
|------|------|
| `cmd/mops/main.go` | 程序唯一 CLI 入口 |
| `pkg/mops/api.go` | RESTful HTTP API 服务 (`/api/v1/nodes`, `/api/v1/status`) |
| `pkg/mops/api_test.go` | [单元测试] RESTful API 路由与响应测试 |
| `pkg/mops/engine.go` | 内存静态引用 GOST 内核，管理监听与负载均衡 Round-Robin |
| `pkg/mops/engine_test.go` | [单元测试] 代理服务与节点更新测试 |
| `pkg/mops/discovery.go` | mDNS 局域网服务广播与搜寻 (`zeroconf`) |
| `pkg/mops/discovery_test.go` | [单元测试] mDNS 发现与解析测试 |
| `pkg/mops/proxy_windows.go` | Windows 注册表系统代理开关 (`golang.org/x/sys/windows/registry`) |
| `pkg/mops/proxy_windows_test.go` | [单元测试] 系统代理开关测试 |
| `pkg/mops/service.go` | Windows 原生系统服务守护 (`kardianos/service`) |
| `pkg/mops/service_test.go` | [单元测试] Windows 系统服务包装测试 |
| `pkg/mops/status.go` | Tailscale 风格 Terminal 控制台表格与速率渲染 |
| `pkg/mops/status_test.go` | [单元测试] 表格格式化与渲染测试 |
| `pkg/mops/cli.go` | Cobra CLI 命令树 (`run`, `status`, `proxy`, `service`) |
| `pkg/mops/cli_test.go` | [单元测试] CLI 命令行树与交互测试 |
| `pkg/mops/exe_integration_test.go` | [集成测试] `mops.exe` 二进制黑盒集成测试 |
| `pkg/mops/integration_test.go` | [集成测试] 端到端多节点代理与负载均衡测试 |

## CLI 结构

```
mops run [options]                                  # 前台运行代理节点
  --server-port INT                                 # Server TCP 端口（默认 10080）
  --client-port INT                                 # Client 代理端口（默认 10081）
  --api-port INT                                    # RESTful API HTTP 端口（默认 10082）
  --listen HOST                                     # Client 监听地址（默认 127.0.0.1）
  --advertise HOST                                  # mDNS 广播地址（默认自动检测）
  --strategy {random,hash}                          # 负载均衡策略（默认 random）

mops status [--watch]                               # 查看终端集群节点与网速表格
mops proxy [on|off|status]                          # 设置/取消/查看 Windows 系统代理
mops service [install|uninstall|start|stop]         # Windows 原生系统服务管理
```

## 目录结构

```
MOPS/
├── cmd/
│   └── mops/
│       └── main.go          # 程序入口
├── pkg/
│   └── mops/
│       ├── api.go           # RESTful HTTP API 服务
│       ├── api_test.go      # RESTful API 单元测试
│       ├── cli.go           # CLI 参数解析与命令 Handler
│       ├── discovery.go     # mDNS 局域网服务广播与搜寻
│       ├── discovery_test.go# mDNS 单元测试
│       ├── engine.go        # 静态 GOST 代理内核与 Round-Robin 链
│       ├── engine_test.go   # 引擎单元测试
│       ├── proxy_windows.go # Windows 注册表代理控制
│       ├── proxy_windows_test.go # 注册表代理单元测试
│       ├── service.go       # Windows 系统服务包装
│       ├── status.go        # Tailscale 风格表格渲染
│       ├── status_test.go   # 视图渲染单元测试
│       └── integration_test.go # 端到端多节点集成测试
├── go.mod                   # Go 模块文件
├── go.sum                   # Go 依赖锁文件
├── build.ps1                # Windows 构建脚本
├── API.md                   # RESTful API 接口文档
├── GOST_INTEGRATION_PLAN.md # 重构方案规范
└── README.md                # 使用说明
```

## 开发与构建

- **构建命令**：`go build -o bin/mops.exe ./cmd/mops` 或 `.\build.ps1`
- **全量测试命令（推荐，在 bin/ 目录下生成并运行测试）**：
  ```powershell
  # 编译测试二进制至 bin/mops.test.exe 并运行（避免在 system Temp 目录运行）
  go test -c -o bin/mops.test.exe ./pkg/mops
  cmd /c "bin\mops.test.exe -test.v"
  ```
  或者直接执行构建与全量测试脚本：
  ```powershell
  .\build.ps1
  ```
- **输出与测试规范**：
  - 规定所有构建产物（`bin/mops.exe`）及测试可执行程序（`bin/mops.test.exe`）**必须统一在项目根目录 `bin/` 目录下编译生成与运行**，严禁使用系统临时目录（`%TEMP%` 或 `/tmp`）。
  - 黑盒集成测试（`exe_integration_test.go`）会自动编译/使用 `bin/mops.exe` 进行黑盒测试。

