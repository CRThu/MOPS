# MOPS — Multi-node Outbound Proxy System

轻量级分布式出口负载均衡系统，通过局域网内多台设备的 IP 聚合，绕过网关单 IP 限速。

## 架构

```
App → :8080 (local-ingress) → egress-chain (round-robin) → LAN节点 :10080 (lan-egress) → 公网
```

- **Server**: 对外出口，监听 TCP 端口，通过 mDNS 广播自己的存在
- **Client**: 本机代理入口，SOCKS5 + HTTP CONNECT，自动发现 Server 并负载均衡
- **Both**: 同时运行 Server + Client + API

## 快速开始

```bash
uv sync
uv run python -m mops run server      # 在出口机上启动 Server
uv run python -m mops run client      # 在主力机上启动 Client
uv run python -m mops run both        # 或者混合模式
```

## CLI 参考

```
mops                                              # 默认 both 模式启动
mops run        [server|client|both] [--port 10080] [--strategy random|hash] [--listen 127.0.0.1] [--weight 1]
mops service install [--mode both] [--port 10080] [--strategy random]
mops service uninstall
mops service start
mops service stop
mops service status
mops service log [-n 50] [-s keyword]             # 查看日志
mops proxy on   [--port 10081]                    # 设置系统全局代理
mops proxy off                                    # 取消系统全局代理
mops proxy status                                 # 查看代理状态
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--port` | 基础端口，所有端口从此衍生 | 10080 |
| `--strategy` | 负载均衡策略: `random` 或 `hash` | random |
| `--weight` | Server 权重 (仅 server 模式) | 1 |
| `--listen` | Client 监听地址 (仅 client/both 模式) | 127.0.0.1 |
| `--service` | 服务模式运行，无交互式输出 | false |
| `--mode` | 安装服务时的模式: server/client/both | both |

### 端口分配

| 组件 | 端口 |
|------|------|
| Server TCP | `base_port` (默认 10080) |
| Client 代理 | `base_port + 1` (默认 10081) |
| REST API | `base_port + 2` (默认 10082) |

## 代理协议

### SOCKS5（无认证）

```
客户端 → Client:0x05 0x01 0x00 (握手)
Client → 客户端: 0x05 0x00 (确认)
客户端 → Client: CONNECT 请求
Client → Server: host:port\n (隧道头)
Server → 目标: TCP 连接
双向转发
```

### HTTP CONNECT

```
客户端 → Client: CONNECT example.com:443 HTTP/1.1\r\n...
Client → 客户端: HTTP/1.1 200 Connection Established\r\n\r\n
Client → Server: host:port\n
双向转发
```

## REST API

```
GET http://127.0.0.1:10082/status
```

响应示例：

```json
{
  "mode": "both",
  "base_port": 10080,
  "strategy": "random",
  "uptime": "3600s",
  "server": {
    "host": "0.0.0.0",
    "port": 10080
  },
  "client": {
    "listen": "127.0.0.1",
    "port": 10081
  },
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
  "active_conns": 5
}
```

## 负载均衡策略

| 策略 | 说明 |
|------|------|
| `random`（默认） | 随机选择节点，流量最均匀 |
| `hash` | 按 `client_ip:target_host` 哈希，会话保持 |

## 健康检查

- **mDNS 广播**: Server 每 60 秒刷新 TTL，Client 自动感知节点加入/离开
- **被动熔断**: 连续 2 次连接失败 → 节点移入观察池，30 秒后自动恢复

## 系统代理

一键设置/取消系统全局代理，流量自动走 MOPS Client：

```bash
mops proxy on              # Windows: 修改注册表; macOS: networksetup; Linux: 写 env 文件
mops proxy off             # 恢复原设置
mops proxy status          # 查看当前代理状态
mops proxy on --port 20081 # 指定端口
```

## 日志

日志自动保存到 `~/.mops/logs/mops.log`（10MB 轮转，保留 7 天）：

```bash
mops service log                   # 最近 50 行
mops service log -n 100            # 最近 100 行
mops service log -s "error"        # 搜索关键词
```

## 系统服务

### Linux (systemd)

```bash
uv run python -m mops service install --mode both --port 10080
uv run python -m mops service start
uv run python -m mops service status
uv run python -m mops service stop
uv run python -m mops service uninstall
```

### Windows (sc)

```powershell
uv run python -m mops service install --mode both --port 10080
uv run python -m mops service start
uv run python -m mops service status
uv run python -m mops service stop
uv run python -m mops service uninstall
```

## 使用示例

### 测试代理连接

```bash
# SOCKS5 代理
curl.exe --proxy socks5://127.0.0.1:10081 http://httpbin.org/ip

# HTTP 代理
curl.exe --proxy http://127.0.0.1:10081 http://httpbin.org/ip
```

### 浏览器配置

在浏览器代理设置中配置：
- 类型: SOCKS5 或 HTTP
- 地址: 127.0.0.1
- 端口: 10081

### 检查状态

```bash
curl http://127.0.0.1:10082/status
```

## 开发

```bash
uv sync --extra dev
uv run pytest tests/ -v --cov=mops
uv run python build.py              # Nuitka 打包
```

### 项目结构

```
mops/
├── mops/                 # 源码
│   ├── __init__.py       # 版本号
│   ├── __main__.py       # CLI 入口
│   ├── protocol.py       # 共享常量 + 日志路径
│   ├── stats.py          # 流量统计
│   ├── tunnel.py         # 双向流量拷贝
│   ├── server.py         # TCP 透传 + mDNS 广播
│   ├── client.py         # SOCKS5 + HTTP CONNECT 代理
│   ├── discovery.py      # mDNS 服务浏览
│   ├── scheduler.py      # 负载均衡 + 熔断
│   ├── api.py            # REST API
│   ├── service.py        # 系统服务管理
│   └── proxy.py          # 系统代理配置
├── tests/                # 测试 (161 个)
├── build.py              # Nuitka 打包脚本
├── pyproject.toml        # 项目配置
├── .gitignore            # Git 忽略规则
└── LICENSE               # Apache License 2.0
```

## License

Apache License 2.0
