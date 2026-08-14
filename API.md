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
      "success_conns": 128,
      "fail_conns": 0,
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
    "client_enabled": true,
    "server_enabled": true,
    "system_proxy": {
      "enabled": true,
      "proxy_server": "127.0.0.1:10081",
      "http_proxy": "http://127.0.0.1:10081",
      "https_proxy": "http://127.0.0.1:10081",
      "no_proxy": "localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,<local>"
    },
    "speed_up": 12850.5,
    "speed_down": 524288.0,
    "bytes_up": 1048576,
    "bytes_down": 52428800,
    "total_nodes": 3,
    "online_nodes": 3,
    "has_chrome": true
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
| `client_enabled` | bool | 客户端 SOCKS5 代理监听是否开启 |
| `server_enabled` | bool | 服务端 TCP 中继服务监听是否开启 |
| `system_proxy` | object | 系统代理注册表与 3 个大写环境变量的当前值 |
| `speed_up` | float64 | 实时上传速率（字节/秒 B/s） |
| `speed_down` | float64 | 实时下载速率（字节/秒 B/s） |
| `bytes_up` | uint64 | 累计上传总字节数 (Byte) |
| `bytes_down` | uint64 | 累计下载总字节数 (Byte) |
| `total_nodes` | int | 当前感知到的全量节点数 |
| `online_nodes` | int | 当前在线（Status = ONLINE）节点数 |

---

## 3. 开关与自定义设置 Windows 系统代理及环境变量

查询或动态开启/关闭/自定义设置 Windows 系统注册表代理及大写环境变量 (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`)。

- **请求路径**: `/api/v1/system-proxy`
- **请求方法**:
  - `GET`: 查询当前系统代理状态与环境变量
  - `POST`: 开启/关闭/自定义代理 (`{"action": "set", "proxy_addr": "127.0.0.1:7890"}` 或 `{"action": "clear"}` 或 `{"action": "on"}`)

### GET / POST 响应示例

```json
{
  "code": 200,
  "message": "system proxy updated successfully",
  "data": {
    "enabled": true,
    "proxy_server": "127.0.0.1:7890",
    "http_proxy": "http://127.0.0.1:7890",
    "https_proxy": "http://127.0.0.1:7890",
    "no_proxy": "localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,<local>"
  }
}
```

---

## 4. 动态开关与查询 SOCKS5 客户端代理

查询或动态开启/停止 SOCKS5 代理监听服务。

- **请求路径**: `/api/v1/client`
- **请求方法**:
  - `GET`: 查询客户端代理监听状态
  - `POST`: 开启/关闭 SOCKS5 监听 (`{"enable": false}`)

### POST 响应示例

```json
{
  "code": 200,
  "message": "client state updated successfully",
  "data": {
    "enabled": false,
    "port": 10081
  }
}
```

---

## 5. 动态开关与查询 TCP 服务端中继

查询或动态开启/停止 TCP 服务端监听服务。

- **请求路径**: `/api/v1/server`
- **请求方法**:
  - `GET`: 查询服务端中继监听状态
  - `POST`: 开启/关闭 TCP 服务端监听 (`{"enable": true}`)

### POST 响应示例

```json
{
  "code": 200,
  "message": "server state updated successfully",
  "data": {
    "enabled": true,
    "port": 10080
  }
}
```

---

## 6. 跨节点文件传输

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

---

## 7. 获取当前文件传输进度

查询当前正在进行或刚完成的文件发送/接收实时百分比与进度信息。

- **请求方法**: `GET`
- **请求路径**: `/api/v1/files/progress`

### 响应示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "file_name": "demo.mp4",
    "transferred_bytes": 52428800,
    "total_bytes": 104857600,
    "percentage": 50.0,
    "status": "TRANSFERRING",
    "direction": "SEND"
  }
}
```

---

## 8. 查询与修改引擎配置（如文件保存路径）

查询当前引擎参数配置或动态修改接收文件的保存目录 `download_dir`。

- **请求路径**: `/api/v1/config`
- **请求方法**:
  - `GET`: 查询当前引擎配置参数
  - `POST`: 动态设置保存路径 (`{"download_dir": "D:/Downloads"}`)

### POST 请求与响应示例

```json
{
  "code": 200,
  "message": "config updated successfully",
  "data": {
    "download_dir": "D:/Downloads"
  }
}
```

---

## 9. 查询与管理 Windows 系统服务常驻

查询 Windows 后台服务安装状态或动态控制服务的安装、卸载、启动与停止。

- **请求路径**: `/api/v1/service`
- **请求方法**:
  - `GET`: 查询服务是否已安装
  - `POST`: 执行服务控制 (`{"action": "install" | "uninstall" | "start" | "stop"}`)

### POST 响应示例

```json
{
  "code": 200,
  "message": "service action install executed successfully"
}
```

---

## 10. 一键启动多通道加速版 Chrome 浏览器

自动探测系统中已安装的 Google Chrome 浏览器路径，并附加 `--disable-http2 --disable-quic --proxy-server=http://127.0.0.1:{client_port}` 参数直接启动，实现突破单长连接限制的多通道并发加速。

- **请求路径**: `/api/v1/browser/launch`
- **请求方法**: `POST`
- **Query 参数 (选填)**: `browser=chrome`

### 响应示例（已安装 Chrome）

```json
{
  "code": 200,
  "message": "已成功启动多通道加速版 Chrome",
  "data": {
    "browser": "chrome",
    "exe_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "args": [
      "--disable-http2",
      "--disable-quic",
      "--proxy-server=http://127.0.0.1:10081"
    ]
  }
}
```

### 响应示例（未安装 Chrome）

```json
{
  "code": 404,
  "message": "未检测到系统中安装的 Google Chrome 浏览器，请先安装 Chrome"
}
```


