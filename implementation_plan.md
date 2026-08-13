# MOPS Phase 2 GUI 客户端分层架构构建、测试覆盖与 Agent 规范同步计划

> [!NOTE]
> **核心设计原则（第一性原理 & 改动最小化 & 单一实现 & 分层架构）**：
> 1. **改动最小化**：零修改 Phase 1 的 Go 后端代码（`cmd/`, `pkg/`）、编译脚本（`build.ps1`）与既有 Go 单元/集成测试。
> 2. **第一性原理 (First-Principles)**：GUI 本质是一个与 Go 本地 API (`127.0.0.1:10082`) 通信的托盘 Popover 视图，使用原生 Fetch 协议，无冗余框架开销。
> 3. **清晰分层架构 (Layered Architecture)**：
>    - **视图层 (Presentation Layer)**：`components/`（纯 UI 组件，只负责渲染与触发事件）；
>    - **状态/业务逻辑层 (State/Domain Layer)**：`lib/store.ts`（集中管理 UI 响应式状态、1.5s 轮询逻辑与异常处理）；
>    - **基础设施/服务层 (Infrastructure/Service Layer)**：`lib/api.ts`（后端 REST API 通信）与 `lib/tauri.ts`（Tauri 原生 Capability 封装，如文件选择与托盘控制）。
> 4. **单一实现 (Single Source of Truth)**：各分层职责明确，每层仅有一个核心入口文件，不散落散装逻辑。

---

## Architecture Overview (GUI 分层架构)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 视图层 (Presentation Layer)                                │
│    components/ (Header, NodeList, SettingsModal, Toast)     │
└──────────────────────────────┬──────────────────────────────┘
                               │ 事件触发 / 数据绑定
┌──────────────────────────────▼──────────────────────────────┐
│ 2. 状态/业务逻辑层 (State/Domain Layer)                       │
│    lib/store.ts (集中响应式状态机、1.5s 定时轮询、状态变更)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ 调用底层 Service
┌──────────────────────────────▼──────────────────────────────┐
│ 3. 基础设施/服务层 (Infrastructure/Service Layer)            │
│    lib/api.ts (REST API Fetch Client)                        │
│    lib/tauri.ts (Tauri Dialog & Tray Native Adapter)        │
└─────────────────────────────────────────────────────────────┘
```

---

## User Review Required

> [!IMPORTANT]
> **分层测试策略**：
> - **单元测试 (Unit Test)**：针对 `lib/api.ts` 与 `lib/tauri.ts`（基础设施层）独立测试数据解析与错误捕获。
> - **集成测试 (Integration Test)**：针对 `lib/store.ts`（业务逻辑层）与 UI 组件进行集成测试，测试轮询、断网 Toast 响应与状态同步。
> - **E2E 端到端测试 (E2E Test)**：使用 Playwright 覆盖完整 Popover 用户交互。

---

## Proposed Changes

---

### 1. GUI 基础设施层 (Infrastructure Layer)

#### [NEW] [gui/src/lib/api.ts](file:///d:/Projects/MOPS/gui/src/lib/api.ts)
- 提供底层 REST Client：请求 `/api/v1/status`, `/api/v1/nodes`, `/api/v1/files/transfer`, `/api/v1/config`, `/api/v1/service`。

#### [NEW] [gui/src/lib/tauri.ts](file:///d:/Projects/MOPS/gui/src/lib/tauri.ts)
- 封装 Tauri 原生 Capability：唤起原生文件/目录选择对话框 (`dialog.open`)，托盘图标显隐交互。

---

### 2. GUI 状态/业务逻辑层 (State/Domain Layer)

#### [NEW] [gui/src/lib/store.ts](file:///d:/Projects/MOPS/gui/src/lib/store.ts)
- **单一状态中心**：管理全局 AppState（在线节点、网速、代理状态、文件传输进度、Toast 异常消息），负责开启与销毁 1.5s 定时轮询器。

---

### 3. GUI 视图层 (Presentation Layer)

#### [NEW] [gui/src/components/Header.svelte](file:///d:/Projects/MOPS/gui/src/components/Header.svelte)
- 顶部状态看板（展示总开关、系统代理 Toggle 开关、实时网速看板）。

#### [NEW] [gui/src/components/NodeList.svelte](file:///d:/Projects/MOPS/gui/src/components/NodeList.svelte)
- 设备卡片列表（展现 mDNS 节点、本机/远端标识，点击“发送文件”触发选择）。

#### [NEW] [gui/src/components/SettingsModal.svelte](file:///d:/Projects/MOPS/gui/src/components/SettingsModal.svelte)
- 设置弹窗（保存目录修改与常驻 Windows 服务安装/卸载）。

#### [NEW] [gui/src/components/Toast.svelte](file:///d:/Projects/MOPS/gui/src/components/Toast.svelte)
- 全局异常 Floating Banner 提示。

#### [NEW] [gui/src/App.svelte](file:///d:/Projects/MOPS/gui/src/App.svelte)
- 视图布局根节点：绑定 `store.ts`，组装基础组件。

---

### 4. 自动化测试套件 (`gui/tests/`)

#### [NEW] [gui/tests/unit_infrastructure.test.ts](file:///d:/Projects/MOPS/gui/tests/unit_infrastructure.test.ts)
- **单元测试**：基础服务层 `api.ts` 与 `tauri.ts` 接口解析与异常逻辑测试。

#### [NEW] [gui/tests/integration_store.test.ts](file:///d:/Projects/MOPS/gui/tests/integration_store.test.ts)
- **集成测试**：`store.ts` 业务逻辑层与组件集成的状态轮询、断网 Toast 响应与状态同步测试。

#### [NEW] [gui/tests/e2e.spec.ts](file:///d:/Projects/MOPS/gui/tests/e2e.spec.ts)
- **E2E 测试**：Playwright 全流程视图与托盘交互测试。

---

### 5. Agent 规范与项目文档同步

#### [MODIFY] [AGENTS.md](file:///d:/Projects/MOPS/AGENTS.md)
- 追加 `gui/` 分层架构定义与 GUI 自动化测试执行命令（`bun run test`）。

#### [MODIFY] [README.md](file:///d:/Projects/MOPS/README.md)
- 补充 Phase 2 GUI 前端开发与构建运行说明。

---

## Verification Plan

### Automated Tests (自动化测试)

1. **Go 后端测试（基线验证）**：
   ```powershell
   .\build.ps1
   ```
2. **GUI 单元与集成测试（Vitest 统一运行）**：
   ```powershell
   cd gui
   bun run test
   ```
3. **GUI E2E 端到端测试（Playwright 运行）**：
   ```powershell
   cd gui
   bun run test:e2e
   ```

### Manual Verification (手动验证)

1. 启动 Go 守护进程与 GUI：`mops run` + `bun tauri dev`。
2. 验证任务栏托盘弹出/失焦收起、一键系统代理开关、文件发送进度与设置落盘。
