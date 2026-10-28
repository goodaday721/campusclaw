## ADDED Requirements

### Requirement: 班级提示词管理

系统 SHALL 提供 `GET /api/prompt` 返回当前用户所在班级的系统提示词，并提供 `PUT /api/prompt`（body `{body}`，非空）供教师更新；学生调用 PUT MUST 返回 403；未登录返回 401。教师保存后的提示词 SHALL 对该班之后的每次回答生效（回答时从数据库实时读取，MUST NOT 依赖重启或缓存）。

#### Scenario: 教师更新班级提示词

- **WHEN** A 班教师调用 `PUT /api/prompt` 提交 `{"body": "你是解题引导员，只给思路不给答案"}`
- **THEN** 系统返回 200，`class_prompts` 表中 A 班记录更新，随后 `GET /api/prompt` 返回新值

#### Scenario: 学生修改提示词被拒

- **WHEN** A 班学生调用 `PUT /api/prompt`
- **THEN** 系统返回 403，`class_prompts` 表不发生变化

### Requirement: 技能管理（单段 source 文本）

系统 SHALL 提供 `GET/POST /api/skills` 与 `PUT/DELETE /api/skills/{id}`。创建与更新接受单段 source 文本，服务端解析行字段：`名称：`→name、`适用条件：`→trigger、`工具：`→tools、`资料：`→subject、`启用：是/否`→enabled，首个空行之后的正文为 description（引导指令本体）；name 与 description MUST 非空，否则返回 400。技能 MUST 属于提交者所在班级；跨班技能的读写返回 404。删除返回 204。学生 MUST NOT 创建、更新或删除技能（写操作 403），且 GET 仅返回启用中的技能。

#### Scenario: 教师创建解题引导技能

- **WHEN** A 班教师调用 `POST /api/skills` 提交含 `名称：方程解题引导`、`启用：是` 与空行后引导正文的 source 文本
- **THEN** 系统返回 201，`skills` 表新增一行：name、trigger、tools、subject、description、source 各字段按解析结果写入且 class_id 为 A 班

#### Scenario: source 缺少引导正文

- **WHEN** 教师调用 `POST /api/skills` 提交只有 `名称：X` 无空行后正文的文本
- **THEN** 系统返回 400 且不写库

#### Scenario: 学生不可写技能

- **WHEN** A 班学生调用 `POST /api/skills` 或 `PUT/DELETE /api/skills/{id}`
- **THEN** 系统返回 403

#### Scenario: 跨班技能不可见不可改

- **WHEN** B 班教师尝试 `PUT`、`DELETE` A 班的技能，或 A 班教师 `GET /api/skills` 列表
- **THEN** 对该 B 班教师返回 404；A 班教师的列表中不出现 B 班技能

### Requirement: 智能体配置

系统 SHALL 提供 `GET/POST /api/agents` 与 `GET/PUT /api/agents/{id}`，字段为 `{name, prompt, skill_ids[], material_ids[], enabled}`；`skill_ids` 与 `material_ids` 引用的技能/材料 MUST 属于本班，否则返回 404。学生 GET 仅返回 `enabled` 的智能体，且 MUST NOT 更新（PUT 403）——提示词与技能开关的权限必须落在服务端，仅靠前端隐藏无效。

#### Scenario: 教师创建绑定技能与材料的智能体

- **WHEN** A 班教师调用 `POST /api/agents` 提交 `{name, prompt, skill_ids:[A班技能], material_ids:[A班材料], enabled:true}`
- **THEN** 系统返回 201，`agents` 与 `agent_skills`、`agent_materials` 关联表写入对应记录

#### Scenario: 绑定跨班技能被拒

- **WHEN** A 班教师提交 `skill_ids` 中含 B 班技能 id
- **THEN** 系统返回 404 且不写库

#### Scenario: 学生视图与权限

- **WHEN** A 班学生调用 `GET /api/agents` 与 `PUT /api/agents/{id}`
- **THEN** 列表仅含 enabled 的智能体；PUT 返回 403

### Requirement: 会话管理与归属隔离

系统 SHALL 提供 `GET/POST /api/conversations` 与 `GET /api/conversations/{id}`。新建会话（body `{agent_id}`）要求智能体属于本班且（对学生）处于启用状态，否则 404；会话归属创建用户与其班级。查询详情返回 `{conversation, messages[]}`；不属于当前用户或跨班的会话一律返回 404。会话标题 SHALL 取首条提问的截断文本。

#### Scenario: 学生新建会话并查看

- **WHEN** A 班学生对启用智能体调用 `POST /api/conversations` 后再 `GET /api/conversations/{id}`
- **THEN** 返回 201 与会话记录；详情响应含该会话全部消息且顺序正确

#### Scenario: 他人或跨班会话不可见

- **WHEN** 同班其他学生或 B 班用户 `GET /api/conversations/{id}` 访问该会话
- **THEN** 系统返回 404，响应不泄露会话存在性

### Requirement: 流式带引用的引导式回答

系统 SHALL 提供 `POST /api/conversations/{id}/messages`（body `{content}` 非空），以 SSE `text/event-stream` 返回回答：先 `event: meta`（`{"status":"ok","citations":[...]}`），再多个 `event: delta`（`{"text":"..."}` 增量文本），最后 `event: done`（`{"message_id":N}`）。回答前 MUST 检索本班知识库（agent.material_ids 非空时按材料过滤）：有命中则 meta 携带 citations 且答案基于资料切片；零命中则回答固定话术"资料中未找到相关内容"、citations 为空且 MUST NOT 调用模型网关。系统提示词 MUST 取 agent.prompt（为空回退班级提示词）并整段注入智能体绑定且启用的技能 description；对话历史 MUST 取服务端 messages 表最近若干条而不信任客户端。user 与 assistant 消息 SHALL 落库，assistant 消息记录 citations 与所用技能名。流开始前的错误（401/400/404/503）SHALL 以普通 JSON 返回。跨班用户对本班智能体/会话发消息 MUST 返回 404，与"无数据"表现一致。

#### Scenario: 命中资料时流式回答并给出引用

- **WHEN** A 班学生向绑定启用技能的智能体发送与本班材料相关的问题
- **THEN** 响应为 `text/event-stream`，依次收到 meta（citations 指向本班材料切片）、多个 delta、done；assistant 消息落库且 citations 非空

#### Scenario: 无命中不编造

- **WHEN** 学生提问与本班资料完全无关的问题
- **THEN** meta 的 citations 为空，回答为"资料中未找到相关内容"，模型网关未被调用

#### Scenario: 关闭技能后回答明显不同

- **WHEN** 教师将智能体绑定的技能停用后，学生就同一问题再次提问
- **THEN** 新回答不再包含该技能的引导语（服务端不再注入该 description），且旧消息保持不变

#### Scenario: 未登录与跨班访问

- **WHEN** 未登录请求或 B 班用户向 A 班会话发送消息
- **THEN** 分别返回 401 JSON 与 404 JSON，且不产生任何消息记录

#### Scenario: Nginx 不缓冲流式响应

- **WHEN** 流式响应经过 Nginx 转发
- **THEN** 响应头含 `X-Accel-Buffering: no`，前端逐段收到 delta 而非一次性收全
