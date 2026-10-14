# Tasks: add-assistant-streaming-chat

## 1. 数据层

- [x] 1.1 新增 `migrations/004_assistant.sql`：`class_prompts`、`skills`、`agents`、`agent_skills`、`agent_materials`、`conversations`、`messages` 七表（IF NOT EXISTS 幂等）；`app/__init__.py`、`tests/conftest.py`、`seeds/seed.py` 的 MIGRATIONS 列表追加该文件
  - verify: `docker compose exec -T api python -c "..."` 或容器内 pytest 后 `SHOW TABLES` 含七张新表；重复运行迁移不报错
- [x] 1.2 `seeds/seed.py` 追加种子：每班默认班级提示词、一条「方程解题引导」技能（source 文本完整可解析）、一个启用智能体（绑定该技能、material_ids 空）
  - verify: 容器内 `SELECT count(*) FROM class_prompts/skills/agents` 每班各 1；重复 seed 不重复插入

## 2. 仓储与服务层

- [x] 2.1 新增 `app/repositories/prompts.py`（get/upsert）、`skills.py`（list/create/update/delete/find）、`agents.py`（list/get/create/update/find，含 skills/materials 关联读写）、`conversations.py`（list/create/get_with_messages/append_message/update_title）
  - verify: pytest 中经路由间接覆盖；所有 SQL 参数化、班级条件强制
- [x] 2.2 新增 `app/services/skill_source.py`：`parse(source)` 解析 名称/适用条件/工具/资料/启用 行字段 + 空行后正文；`name`/`description` 必填否则抛 `SkillSourceError`
  - verify: pytest 单测覆盖标准样例、缺字段、缺正文、全角冒号兼容
- [x] 2.3 `app/services/model_gateway.py` 新增 `chat_stream(config, messages)` 生成器：`stream:true` + `requests stream=True` 逐行解析 `data:`，产出文本增量；`[DONE]` 结束；错误分类沿用现有两异常
  - verify: pytest 用 fake 流式响应断言增量顺序拼接与非流式等价；网关 500 抛 GatewayUnavailable
- [x] 2.4 新增 `app/services/chat.py` 回答管线：归属校验 → agent(prompt/技能/材料) → 系统提示词（agent.prompt 回退班级 prompt + 注入启用技能 description）→ hybrid 检索（top4/摘录2000/材料过滤）→ 0 命中固定话术不调模型 → 流式生成 → 消息落库（citations JSON + skill_name）；历史取库最近 6 条
  - verify: pytest：0 命中不触发 chat_stream；命中时 meta citations 与库中 citations 一致；历史注入来自 messages 表

## 3. 路由层

- [x] 3.1 新增 `app/routes/api_prompt.py`：GET/PUT `/api/prompt`，PUT 仅教师（学生 403），body `{body}` 非空校验
  - verify: pytest：教师 PUT 200 后 GET 为新值；学生 PUT 403；未登录 401
- [x] 3.2 新增 `app/routes/api_skills.py`：GET/POST `/api/skills`、PUT/DELETE `/api/skills/{id}`；POST/PUT 解析 source（失败 400），DELETE 204；跨班 404；学生 GET 仅 enabled、写操作 403
  - verify: pytest：教师建/改/删全链路；学生建 403；source 缺正文 400；A 班教师改 B 班技能 404
- [x] 3.3 新增 `app/routes/api_agents.py`：GET/POST `/api/agents`、GET/PUT `/api/agents/{id}`；skill_ids/material_ids 必须属本班否则 404；学生 GET 仅 enabled、PUT 403
  - verify: pytest：教师建智能体绑定技能与材料；跨班 skill_id 404；学生只见 enabled 且 PUT 403
- [x] 3.4 新增 `app/routes/api_conversations.py`：GET/POST `/api/conversations`（POST `{agent_id}` 须本班且启用否则 404；标题=首问截断）、GET `/{id}`（`{conversation, messages[]}`，非本人/跨班 404）、POST `/{id}/messages` SSE（meta→delta*→done；流前错误 JSON；`X-Accel-Buffering: no`）
  - verify: pytest：学生创建会话 201；他人/跨班会话 404；SSE 响应体含 meta/delta/done 事件且 citations 与检索一致；B 班 token 访问 A 班 agent 404
- [x] 3.5 `app/__init__.py` 注册全部新蓝图
  - verify: `/health` 200 且新端点路由表存在（`url_map`）

## 4. 接口文档

- [x] 4.1 新增 `app/routes/api_docs.py`：`GET /openapi.json` 手写 OpenAPI 3 dict（全部新旧端点、入参出参、错误码、bearerAuth security）+ `GET /swagger/index.html` CDN swagger-ui-dist 静态页
  - verify: 容器内 `curl -s localhost:5000/openapi.json | python -m json.tool` 合法；浏览器打开 `/swagger/index.html` 渲染文档并能 Authorize 试调

## 5. 前端（app/routes/pages.py 内联）

- [x] 5.1 学生侧"解题助手"卡：智能体选择、会话列表、消息区、输入框；fetch ReadableStream 解析 SSE（meta 渲染 citations 链接、delta 逐字渲染、done 收尾）；0 命中显示固定话术
  - verify: 浏览器学生账号提问，答案逐字出现且引用出处可点击打开材料
- [x] 5.2 教师侧"智能体配置"卡：班级提示词编辑保存、技能 source 增删改（回显原文）、智能体配置（名称/提示词/绑定技能/绑定材料/启用开关）
  - verify: 浏览器教师改提示词与技能后，学生下一轮回答风格/引导语随之变化；关闭技能后同一问题回答明显不同

## 6. 测试与 e2e

- [x] 6.1 新增 `tests/test_assistant.py`（+ 按需拆分）：覆盖 3.1–3.4 全部场景与 2.2/2.3 单测；conftest 加 fake chat_stream fixture
  - verify: 容器内 `docker compose exec -T api pytest -q` 全过（现有 76 例零回归）
- [x] 6.2 `e2e_test.py` 追加第 5 课场景：teacher 设 prompt/建技能/建 agent → student 建会话流式提问（离线 fake 网关），断言 SSE 事件序列、citations、落库消息与跨班 404
  - verify: 容器内 `python e2e_test.py` 与宿主机 `python e2e_test.py --http` 全过

## 7. apitest 接口自动化测试

- [x] 7.1 搭 `apitest/`：`run_all.py`（递归发现 cases、登录、执行、生成 report.html）+ `cases/` 按 URL 组织一接口一脚本（`{id}`→`item`），check 含状态码+响应内容+DB 核对；`.gitignore` 加 `apitest/report.html`
  - verify: `docker compose exec -T api python apitest/run_all.py` 全过并生成报告；`git status` 不出现 report.html
- [x] 7.2 用例覆盖至少：登录（/auth/login）、检索（/materials、/search）、提示词（/api/prompt GET/PUT）、技能（/api/skills POST/GET）、创建会话并发消息（/api/conversations POST + messages SSE）
  - verify: 报告中上述每组用例均 PASS，DB 断言（如 skills 行数、messages 最后一条 role=assistant）生效

## 8. 文档与收尾

- [x] 8.1 README 增补：解题助手能力（提示词/技能/智能体/流式会话）、Swagger 入口（/swagger/index.html）、apitest 运行方式
  - verify: 按 README 步骤在新环境可打开 Swagger 并完成一次学生流式提问
- [x] 8.2 浏览器全链路验证：教师配置（提示词+技能+智能体）→ 学生登录建会话流式提问 → 答案逐字渲染 + 引用出处可打开；跨班提问 404 / 无命中话术正确
  - verify: 截图或录屏留痕；DevTools 中 `/api/conversations/{id}/messages` 响应为 `text/event-stream` 且逐步收到 delta
- [x] 8.3 `openspec validate add-assistant-streaming-chat --strict` 通过，tasks 全部勾选后提交
  - verify: 命令退出码 0；`git log` 含本变更 commit
