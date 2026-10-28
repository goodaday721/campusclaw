## ADDED Requirements

### Requirement: MCP 服务器登记与管理

系统 SHALL 提供 `GET/POST /api/mcp/servers` 与 `PUT/DELETE /api/mcp/servers/{id}`（教师专用：学生一律 403；跨班 id 与不存在一律 404，不泄露存在性）。登记字段为 `{name, base_url, token?}`；同班同名再登记 MUST 返回 409。令牌 SHALL 只保存在服务端：任何列表/详情响应 MUST NOT 含令牌原文，只含 `hasToken` 布尔值；前端输入框 MUST 为密码类型且提交后清空不回显。删除服务器 SHALL 保留其历史调用记录（server_id 置空、server_name 保留）。

#### Scenario: 教师登记服务器

- **WHEN** A 班教师 `POST /api/mcp/servers` 提交 `{name:"campus-tools", base_url:"http://mcp-demo:8090", token:"..."}`
- **THEN** 返回 201，记录落库；响应与后续 `GET /api/mcp/servers` 中 `hasToken` 为 true 且任何字段搜不到令牌字符串

#### Scenario: 同名再登记被拒

- **WHEN** A 班教师再次登记同名服务器
- **THEN** 返回 409

#### Scenario: 跨班与学生的权限

- **WHEN** B 班教师 `GET/PUT/DELETE /api/mcp/servers/{A班id}`，或 A 班学生调用任一管理端点
- **THEN** B 班教师得到 404（与不存在一致），学生得到 403

### Requirement: 连接与工具发现

系统 SHALL 提供 `POST /api/mcp/servers/{id}/connect`：取出本班该服务器的地址与令牌，完成 `initialize` 握手与 `tools/list` 发现，任一步失败则停在未连接、清空工具缓存并返回可读原因；成功则用本次清单**整体替换**旧缓存（连续连接两次清单条数不翻倍）并将状态标记为已连接。系统 SHALL 提供 `POST /api/mcp/servers/{id}/disconnect`：清空缓存并标记未连接。`GET /api/mcp/servers/{id}/tools` SHALL 返回最近一次成功的发现结果。连接失败 MUST NOT 阻断第 5 课已有的检索与流式对话主路径。

#### Scenario: 连接后发现工具清单

- **WHEN** 教师对登记正确（地址与令牌与 mcp-server 一致）的服务器点连接
- **THEN** 响应 200，`GET /api/mcp/servers/{id}/tools` 列出 mcp-server 暴露的工具名与参数结构

#### Scenario: 令牌改错连接失败可读

- **WHEN** 修改令牌为错误值后再连接
- **THEN** 返回 400/502 与可读错误（提示检查地址与令牌），状态为未连接、缓存为空

#### Scenario: 断开后不可再调用

- **WHEN** 教师断开服务器后，学生用引用了其工具的技能提问
- **THEN** 该次调用状态为 denied（不静默成功），缓存为空且引用保存被拒

### Requirement: 调用审计查询

系统 SHALL 提供 `GET /api/mcp/call-logs`（教师专用）返回本班 MCP 调用记录（按时间倒序），每条至少含 `tool@server` 引用、状态（ok/denied/error）、触发用户、会话、轮次与时间，成功记结果摘要、失败记原因。记录只覆盖能归属到服务器的调用：服务器已删除/未登记导致的拒绝 MUST NOT 落记录，但 SHALL 在本次应答的 tool_calls 清单中可见。

#### Scenario: 审计记录五问齐备

- **WHEN** 学生一次会话中触发工具调用后，教师 `GET /api/mcp/call-logs`
- **THEN** 新增记录含工具引用与服务器名、状态 ok、该学生、会话 id、轮次与时间

#### Scenario: 审计按班级隔离

- **WHEN** B 班教师查看 call-logs
- **THEN** 列表只含 B 班的调用，A 班触发的记录不出现
