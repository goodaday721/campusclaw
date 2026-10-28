# Proposal: add-assistant-streaming-chat

## Why

第 5 课任务要求把系统升级为"解题助手智能体"：教师设置系统提示词、维护至少一条「解题引导」技能（只引导不给最终答案），学生新建会话提问后经流式（SSE）看到回答；回答前检索本班知识库并显示引用出处；跨班与"资料中未找到相关内容"的表现保持一致。同时要求交付可交互的接口文档（Swagger）与仓库内接口自动化测试目录（`apitest/`）。现有系统只有非流式的 `POST /ask`（一次性返回整段答案），没有提示词/技能/智能体/会话管理能力，无法满足本课验收。

## What Changes

- 新增班级级提示词接口：`GET /api/prompt`、`PUT /api/prompt`（body `{body}`）；教师保存后对之后的回答生效（实现上每次回答时从库中读取）；学生 PUT 返回 403。
- 新增技能管理接口：`GET/POST /api/skills`、`PUT/DELETE /api/skills/{id}`。技能以**单段 source 文本**提交，服务端解析 `名称：`、`适用条件：`、`工具：`、`资料：`、`启用：` 等行字段与首个空行后的正文（引导指令本体）；解析失败返回 400；删除返回 204。
- 新增智能体接口：`GET/POST /api/agents`、`GET/PUT /api/agents/{id}`，字段 `{name, prompt, skill_ids[], material_ids[], enabled}`；skill/material 必须属于本班否则 404；学生只能读到 `enabled` 的智能体，且不可修改提示词与技能开关（权限落服务端）。
- 新增会话与流式消息接口：`GET/POST /api/conversations`（POST body `{agent_id}`，智能体须本班且启用否则 404）、`GET /api/conversations/{id}`（返回 `{conversation, messages[]}`，非本人或跨班一律 404）、`POST /api/conversations/{id}/messages`（body `{content}`）以 **SSE `text/event-stream`** 返回：`event: meta`（含 citations）→ 多个 `event: delta`（增量文本）→ `event: done`（message_id）；流开始前的鉴权/校验错误仍返回普通 JSON（401/400/404/503）；响应头带 `X-Accel-Buffering: no` 防 Nginx 缓冲。
- 回答管线：auth → 读取智能体（prompt/技能/材料范围）→ 系统提示词 = `agent.prompt`（为空回退班级 prompt）+ 注入智能体绑定的启用技能 description → 检索本班知识库（复用第 4 课 hybrid，top4、摘录 2000 字；`material_ids` 非空时按材料过滤，空 = 本班全部）→ 有命中则携带 citations，0 命中直接回答"资料中未找到相关内容"且不调用模型 → 调用课程网关流式生成 → user/assistant 消息落库（assistant 记录 citations JSON 与所用技能名）。历史多轮取 `messages` 表最近若干条（不信任客户端传入）；会话标题 = 首条提问截断。
- 接口文档：新增 `GET /openapi.json`（手写 OpenAPI 3 文档，覆盖全部新旧端点、入参出参、错误码、是否需登录与 BearerAuth security）与 `GET /swagger/index.html`（CDN swagger-ui-dist 静态页），浏览器可直接打开 Swagger UI 并试调。
- 接口自动化测试：仓库新增 `apitest/` 目录——一个接口一个脚本、目录按 URL 组织（如 `cases/api/auth/login/POST.py` 对应 `POST /api/...`），`run_all.py` 一键跑完并生成 HTML 报告（报告不进 Git）；断言不只查状态码，还核对响应内容与数据库一致性；至少覆盖登录、检索、提示词技能、创建会话并发消息。
- 数据层新增迁移 `004_assistant.sql`：`class_prompts`、`skills`、`agents`、`agent_skills`、`agent_materials`、`conversations`、`messages` 七张表；种子数据为每班写入默认提示词 + 一条「方程解题引导」技能 + 一个启用的智能体（material_ids 空 = 本班全部），供直接演示。
- 前端（`pages.py` 内联，延续北大红主题）：学生侧新增"解题助手"卡（选智能体、会话列表、消息区、输入框，fetch ReadableStream 解析 SSE 渲染增量与引用出处）；教师侧新增"智能体配置"卡（提示词编辑、技能 source 增删改、智能体配置）。
- 旧路由（`/auth/login`、`/materials`、`/search`、`/ask`、页面）行为不变。

## Capabilities

### New Capabilities

- `assistant-chat`: 解题助手智能体——班级提示词、技能管理、智能体配置、会话管理与 SSE 流式带引用问答。
- `api-docs`: 接口文档交付——OpenAPI 描述与浏览器可用的 Swagger UI。

### Modified Capabilities

（无——既有能力的行为不变，本变更为纯新增。）

## Non-Goals

- 不做作业提交、批改与错题讲解（第 7 课范围）。
- 不做异步队列与后台任务（第 8 课范围）。
- 不做关怀型对话（与解题助手不同的第二人设）。
- 不做技能注册表与工具真实执行：`工具：` 字段仅作技能元信息随 source 存储，工具不真正注册或调用；技能触发采用"启用即整段注入、关闭即不注入"，不做按"适用条件"的智能匹配。
- 不做 MCP、渐进式披露与多轮 function calling。
- 不做流式以外的传输优化（无 WebSocket、无轮询降级）。
- 不做会话分页、搜索与导出；不做提示词版本历史。
- 不做生产高可用、SSO；系统仍为单实例部署。

## Impact

- **数据层**：新增 `migrations/004_assistant.sql` 与 `seeds/seed.py` 追加种子；`app/__init__.py`、`tests/conftest.py` 迁移列表各加一行。
- **服务层**：新增 `app/services/chat.py`（回答管线）、`app/services/skill_source.py`（source 解析）；`app/services/model_gateway.py` 新增 `chat_stream()`。
- **仓储层**：新增 `app/repositories/{prompts,skills,agents,conversations}.py`。
- **路由层**：新增 `app/routes/{api_prompt,api_skills,api_agents,api_conversations,api_docs}.py` 并在 `app/__init__.py` 注册。
- **前端**：`app/routes/pages.py` 内联 JS 增加学生"解题助手"卡与教师"智能体配置"卡。
- **测试**：新增 `tests/test_assistant.py` 等；`e2e_test.py` 追加第 5 课场景；仓库新增 `apitest/`。
- **文档**：README 增补解题助手与 Swagger 说明。
