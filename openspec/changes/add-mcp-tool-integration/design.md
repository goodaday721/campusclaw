# Design: add-mcp-tool-integration

## 技术栈与组件映射

| 组件 | 实现技术 | 说明 |
|---|---|---|
| MCP 工具服务器 | Python 3.12 + Flask + gunicorn（`mcp-server/` 独立 Dockerfile） | 服务名 `mcp-demo`，容器内 8090，仅内网 |
| 协议报文 | 手写 JSON-RPC 2.0（`POST /mcp` 单端点） | `initialize` / `tools/list` / `tools/call`；令牌校验后分发 |
| 宿主 MCP 客户端 | `app/services/mcp_client.py`（requests） | 三个方法 + 错误分类（不可用/被拒/工具自报错误） |
| 注册表存储 | MySQL `mcp_servers` / `mcp_tools_cache` / `mcp_call_logs`（`migrations/005_mcp.sql`） | 同名唯一（class_id+name）；缓存连接时整体替换 |
| 登记管理路由 | `app/routes/api_mcp.py`（教师 only，学生 403，跨班 404） | 列表响应只含 `hasToken` 布尔值，永不回传令牌原文 |
| 技能引用校验 | `app/services/mcp_service.py`（校验四查：格式/存在/已连接/在清单内） | 工具名 `^[a-z][a-z0-9_]*$`，服务器名允许连字符 |
| 调用循环编排 | `app/services/chat.py` 扩展 + `model_gateway.chat_with_tools`（非流式带 tools） | 循环轮非流式；最终收尾轮流式（不带 tools）保证流式体验 |
| 审计 | `mcp_call_logs` 每调用一行 + `GET /api/mcp/call-logs` | 五问：tool@server、状态、用户、会话+轮次、时间 |
| 前端 | `pages.py` 内联 | 教师侧「MCP 工具服务」卡 + 对话页工具栏（meta.tool_calls 先于正文渲染） |

## 关键决策

1. **meta 一次性携带全部 tool_calls**：课件示例 meta 事件含 `tool_calls`（ref/status/text），且要求调用事件先于正文。因此整个工具循环在 SSE 开始前（`chat.start`）完成——循环轮用非流式 `chat_with_tools`，模型不再提出调用的那一轮 content 丢弃，改用流式收尾轮（消息已含全部工具数据段）生成最终回答。网关错误仍在 SSE 前变 JSON 503，沿用第 5 课 prime 模式。
2. **结果作为数据不是指令**：工具返回文本经指令式句式检查（命中整条丢弃换固定说明）后，以「[工具 ref 返回的数据]」段落拼进用户消息，与检索资料同一数据位通道，不进系统提示。
3. **上限双闸门**：`MAX_TOOL_ROUNDS=3`（一条链深度）+ `MAX_TOOL_CALLS=5`（累计次数），超限后停止调用、流式收尾轮让模型用已有信息作答（优雅降级，不报错）。
4. **拒绝分两级**：服务器已删除/未登记 → `denied` 且不留审计记录（无处归属）；未连接/清单外/参数校验失败/越权 → `denied` 且留记录（可归属）。工具自报错误/超时 → `error` 留记录。三者都在 meta.tool_calls 中可见，不静默成功。
5. **连接失败清空缓存**：握手或发现任一步失败 → 置 disconnected + 清空缓存（「不记住失败的发现结果」，与故障表「未连接时保存引用被拒」一致）；连接成功才整体替换清单。
6. **令牌边界**：令牌只在登记写入与发请求两处出现原文；列表/详情响应只有 `hasToken`；前端输入框 type=password 提交后清空不回显；每台服务器各自令牌。
7. **候选集最小权限**：仅把本轮技能引用到的（已连接、在清单内的）工具转为工具声明发给模型；候选集外模型不可见。声明 name 用工具名，宿主维护 工具名→ref 映射。
8. **seed 预登记不连接**：seed 用 `MCP_AUTH_TOKEN` 环境变量为每班预登记 `campus-tools`（Base URL `http://mcp-demo:8090`），连接动作留给教师/测试脚本（避免启动期依赖 mcp-demo 就绪）。
9. **主路径不受影响**：技能无 MCP 工具时走第 5 课原管线（零改动语义）；连接失败、调用失败只影响工具增益，检索与流式回答照常。

## 风险与取舍

- 网关 `tools` 支持（非流式+流式）已实测确认（标准 OpenAI tool_calls 格式，按 index 增量累积）。
- 流式收尾轮不带 tools，规避「收尾轮再提出调用」的循环终止歧义。
- `mcp_tools_cache.input_schema` 用 MySQL JSON 列存发现结果原样结构。
- 删除服务器时 `mcp_call_logs.server_id` 置 NULL，`server_name` 冗余保留可读记录。
