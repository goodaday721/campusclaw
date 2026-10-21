## ADDED Requirements

### Requirement: 自建 MCP 工具服务器

仓库 SHALL 包含 `mcp-server/` 目录（与主应用同仓），由 `docker-compose.yml` 一并构建启动为内网服务（服务名 `mcp-demo`，不映射宿主机端口）。服务 SHALL 提供 `POST /mcp` 单端点实现 JSON-RPC 2.0 三个方法：`initialize`（返回协议版本与能力）、`tools/list`（返回工具清单，每项含 name/description/inputSchema）、`tools/call`（执行工具并返回 `result.content` 文本数组与 `isError` 标记）；并提供 `GET /health` 存活判定（无需令牌）。无令牌或令牌错误 MUST 返回 401；非法 JSON、缺失 method、未知 method MUST 返回可读的 JSON-RPC 错误（-32700/-32600/-32601）。Bearer 令牌 SHALL 只从环境变量读取（如 `MCP_AUTH_TOKEN`），MUST NOT 进 Git、不进镜像层、不进前端。

#### Scenario: 带令牌握手与发现

- **WHEN** 携带正确 `Authorization: Bearer` 依次发送 `initialize` 与 `tools/list`
- **THEN** initialize 返回服务器信息与能力，tools/list 至少返回 `formula_hint` 与 `unit_convert` 两个工具（名称小写字母开头、无连字符）

#### Scenario: 带令牌调用工具返回文本

- **WHEN** 发送 `tools/call` 调用 `formula_hint`（参数 `{"query":"去括号这一步我不会"}`）
- **THEN** 返回 `result.content` 含文本提示、`isError` 为 false，且内容只给思路提示不给最终数值答案

#### Scenario: 令牌错误被拒

- **WHEN** 不带令牌或令牌错误请求 `/mcp`
- **THEN** 返回 401，不暴露任何工具信息

#### Scenario: 非法请求返回 JSON-RPC 错误

- **WHEN** 发送非法 JSON 或未知 method
- **THEN** 返回带 code（-32700/-32601）与可读 message 的 JSON-RPC error 响应

#### Scenario: Compose 内网互通

- **WHEN** api 容器内访问 `http://mcp-demo:8090/health`
- **THEN** 返回 200；宿主机无法直接访问该服务端口
