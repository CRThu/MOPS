# MOPS

**MOPS (Multi-node Outbound Proxy System)** —— 面向 Windows 平台的 Go 语言高性能单体代理系统 (`mops.exe`)。

静态链接引用 GOST v3 内存级代理内核，通过局域网内多台设备的 IP 聚合与 Round-Robin 轮询，绕过网关单 IP 限速。

## 功能特性

- **静态链接 GOST 内核** — 内存级代理，零外部 `gost.exe` 子进程，零 IPC 开销
- **零配置 mDNS 组网** — 基于原生 Go zeroconf，自动广播并动态更新 Round-Robin 节点轮询链
- **Windows 原生系统服务** — 支持无黑框静默运行 (`Services.msc`)，开机常驻守护
- **Windows 注册表系统代理** — 一键开启/关闭/查看 Windows 系统全局代理
- **Tailscale 风格 CLI 视图** — `mops status` / `mops status -w` 在终端中以美观表格实时显示集群节点与总网速
- **单一可执行文件** — 解压即用，无 Python 运行库与 Web 依赖

## 极速构建

```powershell
# 使用 PowerShell 脚本极速编译
.\build.ps1

# 或使用标准 go build
go build -o mops.exe ./cmd/mops
```

## CLI 命令说明

```powershell
# 启动 MOPS 代理节点
.\mops.exe run

# 查看 Tailscale 风格集群状态 (加上 -w 可实时轮询刷新)
.\mops.exe status -w

# Windows 系统代理控制
.\mops.exe proxy on
.\mops.exe proxy off
.\mops.exe proxy status

# Windows 原生系统服务守护
.\mops.exe service install
.\mops.exe service start
.\mops.exe service stop
.\mops.exe service uninstall
```

### 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--server-port` | Server TCP 监听端口 | `10080` |
| `--client-port` | Client SOCKS5 代理端口 | `10081` |
| `--listen` | 本地绑定地址 | `127.0.0.1` |
| `--advertise` | mDNS 广播 IP | 自动检测 |
| `--strategy` | 负载均衡策略 (`random` / `hash`) | `random` |


### 端口分配

| 组件 | 参数 | 默认端口 |
|------|------|----------|
| Server TCP | `--server-port` | 10080 |
| Client SOCKS5 | `--client-port` | 10081 |

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

