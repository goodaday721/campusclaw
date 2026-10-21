# Proposal: add-mcp-tool-integration

## Why

第 6 课要求「MCP 与工具接入」：理解 MCP 协议与主机/客户端/服务器角色，完成工具发现、绑定与鉴权调用。当前系统（第 5 课后）的解题助手只能检索本班知识库作答，没有外部工具能力。本变更在同仓内新增一个自建 MCP 工具服务器，并在主应用（宿主）侧实现登记、连接发现、技能引用绑定、带令牌的鉴权调用与调用审计，使解题助手能在回答前调用本班登记的工具。

## What Changes

- 新增 `mcp-server/` 目录：一个独立部署的 MCP 工具服务器（与主应用同仓，由 docker-compose 一并构建启动，服务名 `mcp-demo`），提供 `POST /mcp`（JSON-RPC 2.0：`initialize` / `tools/list` / `tools/call`）与 `GET /health`，Bearer 令牌鉴权（令牌仅来自环境变量 `MCP_AUTH_TOKEN`），至少暴露 `formula_hint`、`unit_convert` 两个工具（只给提示/换算，不给最终解题答案）。
- 主应用新增 MCP 注册表：教师登记本班服务器（名称、Base URL、Bearer 令牌——令牌只存服务端，任何接口响应只回「是否已配令牌」布尔值）、连接（握手 + `tools/list` 发现，缓存整体替换并标记已连接）、断开（清空缓存、不可再调用）。
- 技能 source 的「工具」行支持 MCP 引用格式 `工具名@服务器名`（内置 `knowledge_search` 不变）；保存时校验引用格式、服务器存在且已连接、工具在最近发现清单内，否则拒绝保存。
- 学生提问命中带 MCP 工具的技能时，服务端完成调用循环：工具声明随提问发给模型 → 模型提出调用 → 宿主按声明结构校验参数、带令牌执行 `tools/call` → 结果作为数据段（非指令）拼进用户消息 → 可多轮（轮次与累计次数上限，超限优雅降级）→ 最终流式作答。
- 每次 MCP 调用留一条审计记录（tool@server、状态、用户、会话、轮次、时间）；SSE `meta` 事件新增 `tool_calls`（有调用才出现，先于正文 delta）；教师可查看本班调用审计。
- Swagger 文档补充 MCP 管理接口；`apitest/` 增加 MCP 用例。

## Non-Goals

- 不实现 MCP 的 resources / prompts 能力（本课只暴露 tools）。
- 不实现 stdio 传输（只走 HTTP 单端点）。
- 不实现指标与追踪两层可观测性（本课只做日志/审计一层）。
- 不引入第三方 MCP SDK；mcp-server 与宿主客户端均手写 JSON-RPC 报文。
- 不做多实例 api 部署下的分布式锁与并发去重（维持单实例部署约定）。
- 不改动第 3–5 课已有的检索、流式对话主路径——连接失败、工具失败都不阻断主路径。

## Capabilities

### New Capabilities

- `mcp-server`：自建 MCP 工具服务的协议实现与令牌鉴权。
- `mcp-registry`：宿主侧服务器登记、连接发现、断开与调用审计查询。
- `tool-calls`：技能工具引用校验、对话中的调用循环编排、SSE tool_calls 事件。

### Modified Capabilities

- `api-docs`：新增 MCP 管理与审计端点的 OpenAPI 描述。
