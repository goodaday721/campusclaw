# Design: add-assistant-streaming-chat

## Context

第 5 课要求交付"解题助手智能体"：教师可配置提示词与「解题引导」技能，学生经 SSE 流式获得带引用的引导式回答。现有系统（Flask + MySQL 8.0 + Qdrant，Docker 四服务）已具备 Bearer JWT 认证、班级隔离、hybrid 检索与非流式 `POST /ask`。本设计在其上纯增量叠加，不改动既有端点行为。

## Goals / Non-Goals

- Goals：提示词/技能/智能体/会话四组管理接口；SSE 流式带引用回答；Swagger 文档页；`apitest/` 接口自动化测试目录。
- Non-Goals：作业批改、异步队列、关怀对话、MCP、工具真实执行、按"适用条件"的技能智能匹配（启用即整段注入）——见 proposal。

## Decisions

### D1. 新路由全部挂 `/api/` 前缀

旧路由 `/auth/login`、`/materials`、`/search`、`/ask` 不动，避免破坏现有测试与前端。第 5 课新增端点统一 `/api/...`：

| 端点 | 方法 | 权限 | 说明 |
| --- | --- | --- | --- |
| `/api/prompt` | GET | 登录 | 班级提示词（本班） |
| `/api/prompt` | PUT | 教师 | body `{body}`；学生 403 |
| `/api/skills` | GET/POST | 登录/教师 | 列表（学生只见 enabled）/创建 |
| `/api/skills/{id}` | PUT/DELETE | 教师 | 更新/删除；跨班 404 |
| `/api/agents` | GET/POST | 登录/教师 | 列表（学生只见 enabled）/创建 |
| `/api/agents/{id}` | GET/PUT | 登录/教师 | 详情/更新；学生 PUT 403 |
| `/api/conversations` | GET/POST | 登录 | 本人会话列表 / 新建（body `{agent_id}`） |
| `/api/conversations/{id}` | GET | 登录 | `{conversation, messages[]}`；非本人/跨班 404 |
| `/api/conversations/{id}/messages` | POST | 登录 | body `{content}`；SSE 流式回答 |
| `/openapi.json`、`/swagger/index.html` | GET | 公开 | 接口文档 |

### D2. 技能以单段 source 文本提交，服务端解析

学生/教师在前端粘贴一段文本（课件原型样式），服务端逐行解析：

- `名称：X` → `name`；`适用条件：a,b` → `trigger`；`工具：knowledge_search` → `tools`（列表，仅存元信息）；`资料：数学` → `subject`；`启用：是/否` → `enabled`。
- 首个空行之后的剩余文本 → `description`（引导指令本体，注入提示词的部分）。
- `name` 与 `description` 必须非空，否则 400；其余字段可缺省。
- 存表时同时保存原始 `source`，编辑时回显原文。

### D3. 回答管线（chat service）

```
auth → 会话归属校验（本人+本班，否则 404）
     → 读 agent（prompt/skill_ids/material_ids）→ 学生侧 agent 必须 enabled
     → 系统提示词 = agent.prompt 非空取之，否则班级 class_prompts.body
     → 追加 agent 绑定且 enabled 的技能 description（整段注入）
     → hybrid 检索本班（复用 retrieval.search：top4、excerpt_limit=2000；
        agent.material_ids 非空 → 结果按材料过滤）
     → 0 命中：直接回"资料中未找到相关内容"，citations=[]，不调模型
     → 命中：构造 citations；历史取 messages 表最近 6 条（不信任客户端）
     → model_gateway.chat_stream 流式产出 delta（event: delta）
     → 落库 user/assistant 消息（assistant 带 citations JSON + skill_name）
```

SSE 事件序列：`event: meta\ndata: {"status":"ok","citations":[...]}` → 多个 `event: delta\ndata: {"text":"..."}` → `event: done\ndata: {"message_id":N}`。0 命中时 meta 照发（citations 为空），delta 一条后 done——前端表现与"无数据"一致。流开始前的错误（鉴权 401、参数 400、会话/智能体 404、网关 503）仍返回普通 JSON，前端按非流式处理。响应头 `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`（Nginx 不缓冲）。

### D4. 网关流式：`model_gateway.chat_stream()`

OpenAI 兼容 `POST /chat/completions` 带 `"stream": true`，`requests.post(..., stream=True)` 逐行解析 `data:` 行，`[DONE]` 结束；每片取 `choices[0].delta.content` 拼接产出生成器。错误分类沿用 `GatewayUnavailable`（503）/`GatewayRejected`（400）。读超时需放宽（流式首字节后每片间隔短，仍用现有 read 超时即可）。

### D5. 数据模型（迁移 004_assistant.sql）

- `class_prompts(class_id PK, body TEXT, updated_at)`——每班一行。
- `skills(id, class_id, name, trigger, tools JSON, subject, description TEXT, source TEXT, enabled TINYINT, created_at, updated_at)`。
- `agents(id, class_id, name, prompt TEXT, enabled TINYINT, created_at, updated_at)`；`agent_skills(agent_id, skill_id)`、`agent_materials(agent_id, material_id)` 两张关联表（均含级联删除）。
- `conversations(id, user_id, class_id, agent_id, title, created_at, updated_at)`。
- `messages(id, conversation_id, role ENUM('user','assistant'), content MEDIUMTEXT, citations JSON NULL, skill_name VARCHAR NULL, created_at)`。

种子（幂等）：每班默认班级提示词 + 1 条「方程解题引导」技能（source 含 名称/适用条件/工具/资料/启用 + 正文）+ 1 个启用智能体（绑定该技能，material_ids 空 = 本班全部）。

### D6. Swagger：手写 dict + CDN 静态页

`GET /openapi.json` 返回手写 Python dict（OpenAPI 3.0），覆盖全部新旧端点：路径/方法、入参（body schema、query）、出参、错误码（401/400/403/404/503）、`security: [{bearerAuth: []}]` 标注需登录端点，`components.securitySchemes` 声明 BearerAuth。`GET /swagger/index.html` 返回引用 CDN `swagger-ui-dist` 的静态 HTML（`url: '/openapi.json'`），零本地依赖，浏览器打开即可试调（Swagger UI 自带 Authorize 按钮粘贴 token）。

### D7. apitest：容器内运行、按 URL 组织、DB 核对

- 目录 `apitest/`：`cases/` 下一个接口一个脚本，目录按 URL 路径组织（`{id}` 用 `item` 表示，如 `cases/api/skills/item/PUT.py`）；脚本暴露 `CASE`（name/method/path/body/前置登录角色/`check(resp, ctx)`）。
- `check` 断言三层：状态码、响应内容（JSON 字段/文本）、数据库一致性（容器内 pymysql 直连 `db` 核对行数与字段）。
- `run_all.py` 递归发现 `cases/**/[A-Z]*.py`，登录取 token，逐个执行并生成 `apitest/report.html`（加入 `.gitignore`，报告不进 Git）。
- 运行方式：`docker compose exec -T api python apitest/run_all.py`；请求基址 `http://web:80`（走 Nginx 真链路），DB 核对连 `db`。覆盖至少：登录、检索（materials/search）、提示词与技能（GET/PUT/POST）、创建会话并发消息（SSE 读取）。

## Risks / Trade-offs

- SSE 经过 Nginx 需禁用缓冲：已加 `X-Accel-Buffering: no`；Nginx 现有配置无需改动（响应头级控制）。
- 流式过程中网关中断：已产出的 delta 无法撤回，done 事件缺失时前端提示"回答中断"；消息不落库（与"先完成后落库"一致）。
- 单技能全量注入可能超长：技能 description 与知识库摘录均有长度上限（摘录 2000 字），可接受。
- 测试不依赖外网：pytest 用 fake chat_stream（离线确定性分片）；apitest 在容器内也走同一路径（网关可用时为真流式，不可用时 503 场景亦可断言）。

## Migration Plan

新增 `004_assistant.sql` 全部 `CREATE TABLE IF NOT EXISTS`，幂等可重复执行；启动时 `_init_db` 自动执行迁移与种子。无数据回填、无破坏性变更。

## Open Questions

（无）
