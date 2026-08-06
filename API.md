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

---

## 3. 跨节点文件传输

将本地指定路径的文件通过 MOPS 分布式 TCP 通道安全流式传输至目标节点，自动校验 SHA256 完整性及防覆盖重命名。

- **请求方法**: `POST`
- **请求路径**: `/api/v1/files/transfer`
- **URL Query 参数**:
  - `target_ip` (string, 必填): 目标节点的 IP 地址
  - `target_port` (int, 选填): 目标节点的 Server 端口，默认 `10080`
  - `path` (string, 选填): 本地要发送的文件绝对/相对路径。系统自动解析文件名、字节大小与计算 SHA256。

### 请求示例

```bash
curl -X POST "http://127.0.0.1:10082/api/v1/files/transfer?target_ip=192.168.132.74&path=D:/movies/demo.mp4"
```

### 响应示例

```json
{
  "code": 200,
  "message": "file transfer completed successfully",
  "data": {
    "target_ip": "192.168.132.74",
    "target_port": 10080,
    "file_name": "demo.mp4",
    "file_size": 104857600,
    "file_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
}
```

