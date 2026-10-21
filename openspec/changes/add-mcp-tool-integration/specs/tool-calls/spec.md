## ADDED Requirements

### Requirement: 技能工具引用格式与保存前校验

技能 source 的「工具」行 SHALL 在内置 `knowledge_search` 之外支持 MCP 引用格式 `工具名@服务器名`（如 `formula_hint@campus-tools`）。工具名 MUST 以小写字母开头且不含连字符（`^[a-z][a-z0-9_]*$`）；服务器名允许连字符。保存（创建/更新）技能时 SHALL 执行四查：格式（解析时立即拒绝并给出可用写法）、服务器已登记（本班）、当前已连接、工具在最近一次发现清单内——任一不过 MUST 返回 400 与可读错误。缺 `@服务器名` 的裸工具名（knowledge_search 除外）与大写工具名 MUST 被拒绝。运行期（对话时）SHALL 再判一次「当前已连接」，配置期从严、运行期从简。

#### Scenario: 合法引用保存成功

- **WHEN** 教师在服务器已连接时保存工具行为 `工具：knowledge_search, formula_hint@campus-tools` 的技能
- **THEN** 返回 201，tools 字段同时含内置项与 MCP 引用

#### Scenario: 格式错误当场拒绝

- **WHEN** 保存工具行为 `Formula_Hint@campus-tools`、`formula-hint@campus-tools` 或 `formula_hint` 的技能
- **THEN** 均返回 400，错误信息说明可用写法

#### Scenario: 未连接时保存被拒

- **WHEN** 服务器处于未连接（或被断开）时保存引用其工具的技能
- **THEN** 返回 400，提示连接后重试；连接成功后同一 source 保存成功

### Requirement: 对话中的工具调用循环

学生提问命中带 MCP 工具引用的技能时，宿主 SHALL 只把本轮引用到的（已连接且在清单内的）工具转换为工具声明（候选集最小权限）随提问发给模型；模型提出调用后，宿主 MUST 按发现结果的 inputSchema 校验参数、携带该服务器各自的 Bearer 令牌执行 `tools/call`——模型与前端 MUST NOT 接触地址与令牌。调用 SHALL 受轮次（≤3）与累计次数（≤5）双上限约束，超限后优雅降级：停止调用，让模型基于已有信息流式作答，而非报错。工具返回文本 SHALL 经指令式句式检查（命中整条丢弃换固定说明）后，作为数据段落进用户消息（不进系统提示、不当作指令）。失败的调用（未连接/越权/参数不合法/工具出错）MUST NOT 中断对话主路径，并如实告知模型。

#### Scenario: 命中工具的提问获得工具增强回答

- **WHEN** 学生向绑定含 `unit_convert@campus-tools` 技能的智能体提问「3千克等于多少克」
- **THEN** 服务端以该学生身份执行一次 `tools/call`（带令牌），换算结果作为数据段进入消息，最终回答用到了工具返回

#### Scenario: 循环有终止也有上限

- **WHEN** 模型连续多轮提出调用直至轮次上限
- **THEN** 超限后不再执行调用，仍流式产出一段基于已有信息的回答（无错误响应）

#### Scenario: 工具结果进数据位不进指令位

- **WHEN** 检查收尾轮发给模型的消息
- **THEN** 工具返回以「[工具 … 返回的数据]」形式出现在用户消息侧，系统提示中无工具返回内容

#### Scenario: 服务器未连接时运行期拒绝

- **WHEN** 学生提问时引用的服务器已被断开
- **THEN** 该引用状态为 denied（不静默成功），对话照常产出回答

### Requirement: SSE meta 携带 tool_calls 且先于正文

流式响应的 `meta` 事件 SHALL 在确有工具调用时携带 `tool_calls` 数组（每项含 `ref`（`工具名@服务器名`）、`status`（ok/denied/error）、`text`（结果摘要或失败原因）、`round`）；技能不带 MCP 工具或本次无调用时 MUST 省略该键（不给空数组）。`tool_calls` MUST 先于任何正文 `delta` 到达；`delta*` 与 `done` 语义与第 5 课一致。流开始前的错误仍以普通 JSON 返回。

#### Scenario: 调用事件先于正文

- **WHEN** 学生触发工具调用的提问返回 SSE
- **THEN** 帧序列为 meta（含 tool_calls）→ delta* → done，第一个 delta 之前已能看见用了哪个工具及状态

#### Scenario: 无调用时省略键

- **WHEN** 学生向未绑定 MCP 工具的智能体提问
- **THEN** meta 中不存在 tool_calls 键，帧序列与第 5 课一致
