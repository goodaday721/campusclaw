## MODIFIED Requirements

### Requirement: 流式带引用的引导式回答

系统 SHALL 提供 `POST /api/conversations/{id}/messages`（body `{content}` 非空），以 SSE `text/event-stream` 返回回答：先 `event: meta`（`{"status":"ok","citations":[...]}`），再多个 `event: delta`（`{"text":"..."}` 增量文本），最后 `event: done`（`{"message_id":N}`）。回答前 MUST 检索本班知识库（agent.material_ids 非空时按材料过滤）：有命中则 meta 携带 citations 且答案基于资料切片。零命中时：若本轮智能体绑定的启用技能未引用任何 MCP 工具，SHALL 回答固定话术"资料中未找到相关内容"、citations 为空且 MUST NOT 调用模型网关；若引用了 MCP 工具，SHALL 照常执行工具循环——至少一次工具调用返回 ok 时基于工具数据调用模型流式回答（citations 保持为空、meta 携带 tool_calls），否则仍回固定话术且 MUST NOT 调用模型网关（meta 如实携带 denied/error 的 tool_calls）。系统提示词 MUST 取 agent.prompt（为空回退班级提示词）并整段注入智能体绑定且启用的技能 description；对话历史 MUST 取服务端 messages 表最近若干条而不信任客户端。user 与 assistant 消息 SHALL 落库，assistant 消息记录 citations 与所用技能名。流开始前的错误（401/400/404/503）SHALL 以普通 JSON 返回。跨班用户对本班智能体/会话发消息 MUST 返回 404，与"无数据"表现一致。

#### Scenario: 命中资料时流式回答并给出引用

- **WHEN** A 班学生向绑定启用技能的智能体发送与本班材料相关的问题
- **THEN** 响应为 `text/event-stream`，依次收到 meta（citations 指向本班材料切片）、多个 delta、done；assistant 消息落库且 citations 非空

#### Scenario: 无命中不编造

- **WHEN** 学生向未引用 MCP 工具的智能体提问与本班资料完全无关的问题
- **THEN** meta 的 citations 为空且无 tool_calls 键，回答为"资料中未找到相关内容"，模型网关未被调用

#### Scenario: 零命中时工具成功仍可回答

- **WHEN** 学生向绑定引用 `unit_convert@campus-tools` 技能的智能体提问「10千克等于多少克」，知识库零命中
- **THEN** 服务端执行 tools/call，meta 携带 status=ok 的 tool_calls 且 citations 为空，回答为基于工具返回数据的流式文本并落库（citations 为空）

#### Scenario: 零命中且工具全部失败仍回固定话术

- **WHEN** 知识库零命中且本轮所有工具调用均 denied/error
- **THEN** meta 携带 denied/error 的 tool_calls，回答为"资料中未找到相关内容"，模型网关未被调用

#### Scenario: 关闭技能后回答明显不同

- **WHEN** 教师将智能体绑定的技能停用后，学生就同一问题再次提问
- **THEN** 新回答不再包含该技能的引导语（服务端不再注入该 description），且旧消息保持不变

#### Scenario: 未登录与跨班访问

- **WHEN** 未登录请求或 B 班用户向 A 班会话发送消息
- **THEN** 分别返回 401 JSON 与 404 JSON，且不产生任何消息记录

#### Scenario: Nginx 不缓冲流式响应

- **WHEN** 流式响应经过 Nginx 转发
- **THEN** 响应头含 `X-Accel-Buffering: no`，前端逐段收到 delta 而非一次性收全
