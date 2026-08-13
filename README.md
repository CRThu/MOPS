# MOPS

**MOPS (Multi-node Outbound Proxy System)** —— 面向 Windows 平台的 Go 语言高性能单体代理系统 (`mops.exe`)。

静态链接引用 GOST v3 内存级代理内核，通过局域网内多台设备的 IP 聚合与 Round-Robin 轮询，绕过网关单 IP 限速。

## 功能特性

- **静态链接 GOST 内核** — 内存级代理，零外部 `gost.exe` 子进程，零 IPC 开销
- **跨节点文件传输 REST API** — 自动进行 1MB 单次高效缓冲、Trailer Hash 校验及同名重命名保护
- **零配置 mDNS 组网** — 基于原生 Go zeroconf，自动广播并动态更新 Round-Robin 节点轮询链
- **Windows 原生系统服务** — 支持无黑框静默运行 (`Services.msc`)，开机常驻守护
- **Windows 注册表系统代理** — 一键开启/关闭/查看 Windows 系统全局代理
- **Tailscale 风格 CLI 视图** — `mops status` / `mops status -w` 在终端中以美观表格实时显示集群节点与总网速
- **Tauri 2.0 高颜值 GUI 客户端** — 基于 Svelte 5 + TailwindCSS 构建 Windows 右下角托盘 Popover 小窗，分层架构封装，零改动 Go 内核

## 极速构建

```powershell
# 1. 使用 PowerShell 脚本极速编译 Go 后端
.\build.ps1

# 2. 运行 GUI 桌面端与测试套件 (需 Node/Bun 环境)
cd gui
bun install         # 安装前端依赖
bun run test        # 运行 Vitest 单元与集成测试 (unit & integration)
bun run test:e2e    # 运行 Playwright 端到端 E2E 测试
bun tauri dev       # 启动 Tauri 2.0 桌面开发小窗
```

## CLI 命令说明

```powershell
# 启动 MOPS 代理节点
.\mops.exe run

# 查看 Tailscale 风格集群状态 (加上 -w 可实时轮询刷新)
.\mops.exe status -w

# Windows 系统代理与环境变量控制 (支持自定义地址/清空)
.\mops.exe proxy on
.\mops.exe proxy set 127.0.0.1:7890
.\mops.exe proxy clear
.\mops.exe proxy off
.\mops.exe proxy status

# 动态开启/关闭/查看 SOCKS5 客户端与 TCP 服务端代理
.\mops.exe client on|off|status
.\mops.exe server on|off|status

# Windows 原生系统服务守护 (标准自动安装至 C:\Program Files\MOPS\)
.\mops.exe service install
.\mops.exe service update
.\mops.exe service start
.\mops.exe service stop
.\mops.exe service uninstall
```

### 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--server-port` | Server TCP 监听端口 | `10080` |
| `--client-port` | Client SOCKS5 代理端口 | `10081` |
| `--api-port` | RESTful API 端口 | `10082` |
| `--download-dir` | 文件接收保存目录 | `./downloads` |
| `--listen` | 本地绑定地址 | `127.0.0.1` |
| `--advertise` | mDNS 广播 IP | 自动检测 |
| `--strategy` | 负载均衡策略 (`random` / `hash`) | `random` |


### 端口分配

| 组件 | 参数 | 默认端口 |
|------|------|----------|
| Server TCP | `--server-port` | 10080 |
| Client SOCKS5 | `--client-port` | 10081 |
| RESTful API | `--api-port` | 10082 |

---

## 代理协议与测试

### curl 测试

```powershell
# SOCKS5 代理请求
curl.exe -x socks5://127.0.0.1:10081 https://ifconfig.me
```

---

## 负载均衡与自动发现

| 特性 | 说明 |
|------|------|
| **Round-Robin** | 默认在所有 ONLINE 节点间加权轮询平摊流量 |
| **mDNS 自动发现** | 基于 zeroconf 原生 Go 广播，无需手动配置 IP |

---

## 许可证

[Apache License 2.0](LICENSE)


