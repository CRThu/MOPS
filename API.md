# MOPS RESTful API 文档

MOPS 在本地后台守护进程运行期间提供 HTTP RESTful API 服务（默认监听端口 `10082`，可通过 `--api-port` 命令行参数进行自定义）。

---

## 基础信息

- **默认基础 URL**: `http://127.0.0.1:10082` (支持通过 `--api-port` 指定其他端口)
- **数据交互格式**: `JSON` (`Content-Type: application/json; charset=utf-8`)

---

## 通用响应结构

RESTful API 返回的标准 JSON 结构体如下：

```json
{
  "code": 200,
  "message": "success",
  "data": ...,
  "total": 1
}
```

---

## 1. 获取集群 mDNS 设备与节点列表

获取当前本地引擎记录的所有代理节点，包括 mDNS 局域网自动感知的节点、显示配置的节点以及本机节点。

- **请求方法**: `GET`
- **请求路径**: `/api/v1/nodes`

### 响应示例

```json
{
  "code": 200,
  "message": "success",
  "total": 1,
  "data": [
    {
      "id": "Windows-PC@192.168.132.74:10080",
      "hostname": "Windows-PC",
      "ip": "192.168.132.74",
      "port": 10080,
      "role": "Both",
      "status": "ONLINE",
      "active_conns": 0,
      "bytes_up": 1048576,
      "bytes_down": 5242880,
      "last_seen": "2026-08-06T16:00:00+08:00",
      "is_me": true
    }
  ]
}
```

---

## 2. 获取本机节点实时网速与状态

获取当前机器运行的 MOPS 引擎状态、监听端口、全网在线节点数以及 **实时传输网速** 与 **累计上传/下载流量**。

- **请求方法**: `GET`
- **请求路径**: `/api/v1/status`

### 响应示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "hostname": "Windows-PC",
    "strategy": "random",
    "client_port": 10081,
    "server_port": 10080,
    "api_port": 10082,
    "speed_up": 12850.5,
    "speed_down": 524288.0,
    "bytes_up": 1048576,
    "bytes_down": 52428800,
    "total_nodes": 3,
    "online_nodes": 3
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `hostname` | string | 本机节点主机名 |
| `strategy` | string | 负载均衡算法（`random` 或 `hash`） |
| `client_port` | int | SOCKS5 代理监听端口 |
| `server_port` | int | MOPS 节点中继服务 TCP 端口 |
| `api_port` | int | 当前 HTTP RESTful API 服务端口 |
| `speed_up` | float64 | 实时上传速率（字节/秒 B/s） |
| `speed_down` | float64 | 实时下载速率（字节/秒 B/s） |
| `bytes_up` | uint64 | 累计上传总字节数 (Byte) |
| `bytes_down` | uint64 | 累计下载总字节数 (Byte) |
| `total_nodes` | int | 当前感知到的全量节点数 |
| `online_nodes` | int | 当前在线（Status = ONLINE）节点数 |
