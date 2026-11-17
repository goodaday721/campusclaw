## 价值

为校园教学提供最小可用的身份认证、角色权限、班级数据隔离、知识库材料管理闭环、限定班级范围且可溯源的知识库检索问答、教师可配置且流式输出的「解题助手」智能体、可登记外部 MCP 工具服务器并由宿主代为执行工具调用的智能体能力，作业提交与异步批改（任务入队、worker 消费者、结果轮询），以及**错题本与错题讲解技能**（低分提交自动沉淀为错题，按错因做诊断式讲解），作为后续教学功能的安全底座。

## 场景

教师向本班知识库投放教学材料，并配置班级提示词、「解题引导」技能与智能体（绑定技能/材料/工具）；学生可在本班材料中按关键字/语义检索具体切片、查看出处并打开原文件，可以就本班材料提问，也可以在解题助手会话中逐步获得引导式回答——回答以 SSE 流式逐字输出，先展示引用出处与工具调用状态，无依据时明确告知而不编造。

## 本学期不做

SSO/生产高可用、MCP resources/prompts 能力与第三方 MCP SDK 接入、技能的智能匹配（工具由技能显式引用、宿主按需代执行）、横向扩展与优先级队列。

## 快速开始（Docker Compose，唯一交付形态）

前置要求：仅安装 Docker Desktop（含 Docker Compose v2），无需 Python/MySQL 本机环境。

```bash
# 1. 准备环境变量（填写数据库密码等必填项）
cp .env.example .env
#    编辑 .env：DB_PASSWORD、DB_ROOT_PASSWORD、JWT_SECRET 必须改成你自己的值
#    （JWT_SECRET 可用 python -c "import secrets; print(secrets.token_hex(32))" 生成）
#    使用向量检索/问答还需填写 EMBED_API_KEY/EMBED_MODEL 与 CHAT_API_KEY/CHAT_MODEL

# 2. 一键构建并启动（web / api / db / qdrant / mcp-demo / worker 六服务）
docker compose up --build -d

# 3. 查看服务状态（六个服务均应为 running）
docker compose ps

# 4. 验证
#    存活检查：http://localhost:8080/health        → {"status":"ok"}
#    就绪检查：http://localhost:8080/health/ready  → 200（db/qdrant 均可达）或 503（有依赖不可用）
#    登录页：  http://localhost:8080/login
```

> web 服务是唯一映射宿主机端口的入口（默认 8080，由 `.env` 的 `WEB_PORT` 控制）；
> api、MySQL、Qdrant 与 worker 均只在 Compose 内部网络，宿主机无法直连。
> 模型网关（嵌入/对话）仅由 api 服务端调用，浏览器拿不到网关密钥，也不能直连向量库。

## 预置账号

首次启动时自动建库、迁移并写入以下演示数据（两个班、两份班级材料，种子材料自动按 auto 策略完成切片）：

| 账号 | 密码 | 角色 | 班级 |
| --- | --- | --- | --- |
| teacher_a | teacher_a_pass | 教师 | A班 |
| student_a | student_a_pass | 学生 | A班 |
| teacher_b | teacher_b_pass | 教师 | B班 |
| student_b | student_b_pass | 学生 | B班 |

## 认证方式（JWT Bearer Token）

登录采用 token 方案：`POST /auth/login` 校验账号密码后签发 **HS256 JWT**（payload 仅含
`sub`/`jti`/`iat`/`exp`，不含角色与班级），token 存于浏览器 `localStorage`，后续请求全部携带
`Authorization: Bearer <token>` 请求头；服务端同时将 `jti` 登记到 `sessions` 表以支持即时撤销。
角色与班级每次请求都从数据库实时读取，token payload 声明一律忽略。

```bash
# 登录：响应体返回 token 与用户信息（不使用 Cookie）
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"teacher_a","password":"teacher_a_pass"}'

# 调用受保护接口：携带 Authorization 请求头
curl http://localhost:8080/materials -H "Authorization: Bearer <登录返回的token>"

# 登出：服务端删除会话记录，原 token 立即失效
curl -X POST http://localhost:8080/auth/logout -H "Authorization: Bearer <token>"
```

浏览器行为：登录后 token 自动保存并在页面内自动附带；退出登录会同时撤销服务端会话并清除本地 token。
`JWT_SECRET` 是 token 签名密钥（`.env` 必填项），更换后所有已签发 token 立即失效，需重新登录。

## 知识库检索与问答（第 4 课）

登录 Dashboard 后可使用「知识库检索」与「知识库问答」两块功能；接口同样可直接调用：

- `POST /search`：body `{"query": "...", "mode": "keyword|vector|hybrid"}`，默认 hybrid。
  每条命中返回材料标题、切片序号、字符区间、正文摘录与打开材料链接，全部只限本班。
- `POST /ask`：body `{"question": "...", "history": [...]}`；先在本班混合检索取前 4 条切片，
  无依据时返回固定文案「资料中未找到相关内容」且 `citations` 为空（不调用对话模型）；
  有依据时回答以 [1][2] 标注，标注顺序与 citations 一致。
- `POST /materials/<id>/reindex`：教师可按 auto/custom/hierarchy 策略重建本班材料索引。

实现要点：

- 正文切为切片存入 MySQL `knowledge_chunks`（ngram 全文索引，token=2）；**向量库只存向量与标识，不存正文**。
- 关键字检索只查 MySQL（不依赖向量库/模型网关）；向量检索余弦相似度阈值 0.35；
  混合检索两路独立过滤后按 RRF（k=60）融合。
- 检索班级只取自登录 token 解析出的实时身份（数据库读取）；请求体伪造 class_id 一律无效；跨班检索表现为 200 + 空命中。
- 上传材料事务提交后才执行切分/嵌入；索引失败不影响已提交材料，切片标记 `failed`，可由教师重建。

### 模型网关配置（可选，只影响向量/问答）

在 `.env` 中填写课程 OpenAI 兼容网关配置：`EMBED_BASE_URL`、`EMBED_API_KEY`、`EMBED_MODEL`、
`CHAT_BASE_URL`、`CHAT_API_KEY`、`CHAT_MODEL`（地址默认指向课程网关，密钥只进本地 `.env`）。
**未配置密钥时系统完全正常启动**：关键字检索、上传下载、认证授权均可用；
向量/混合检索与问答返回 503 并提示依赖不可用。

## 解题助手智能体（第 5 课）

教师登录后在「智能体配置」卡完成三件事，学生端即时生效：

- **班级提示词**：`GET/PUT /api/prompt`，仅教师可写；保存后从下一轮回答开始生效。
- **解题引导技能**：`POST /api/skills` 以单段 source 文本提交（`名称：/适用条件：/工具：/资料：/启用：` 行字段 + 空行后的引导正文），服务端解析入库；技能只做引导、不给最终答案，启用即整段注入提示词，停用后同问题回答明显不同。
- **智能体**：`GET/POST /api/agents` 创建并绑定启用技能与材料范围；学生只读启用项，权限校验全部落在服务端。

学生登录后在「解题助手」卡新建会话（`POST /api/conversations`）并提问（`POST /api/conversations/<id>/messages`）：

- 回答以 **SSE**（`text/event-stream`）流式返回：`meta`（引用出处）→ 多个 `delta`（逐字增量）→ `done`；回答前先检索本班知识库，引用与后端 `citations` 一致。
- 无命中且技能未引用 MCP 工具时返回固定文案「资料中未找到相关内容」且不调用模型；技能引用了工具时仍先执行工具循环，有成功的工具数据才基于其流式回答（`citations` 仍为空）。会话归属班级+用户双校验，跨班一律 404。
- 历史多轮：服务端自动携带最近 6 轮对话；流式中断时不落库，前端提示「（回答中断）」。

## MCP 工具服务（第 6 课）

教师可在「🔌 MCP 工具服务」卡登记外部 MCP 服务器（JSON-RPC 2.0 单端点，Streamable HTTP 传输，Bearer 令牌鉴权），连接后服务端缓存其工具清单（`initialize` / `tools/list`），学生提问命中带工具引用的技能时由宿主（api）代为执行工具调用（`tools/call`）：

- 同仓库 `mcp-server/` 内置演示服务器（campus-tools：`formula_hint` 公式/步骤提示、`unit_convert` 单位换算），首次启动自动预登记到各班（不自动连接），令牌取 `.env` 的 `MCP_AUTH_TOKEN`，未配置则跳过预登记。
- 技能 source 的「工具：」行支持 `工具名@服务器名` 引用（如 `unit_convert@campus-tools`），保存时四查校验（格式/已登记/已连接/在最近发现清单内），不合法即 400 可读错误。
- 工具调用循环：模型提出调用（OpenAI tools 协议）→ api 校验参数并携带该服务器令牌执行 → 结果经指令式句式安全检查后作为数据拼回上下文 → 最多 3 轮、累计 5 次，超限优雅降级为普通回答。检索零命中不阻断工具循环（如「10千克等于多少克」这类纯换算问题也能触发工具），但工具全部失败时仍回固定文案。
- SSE `meta` 事件先于正文携带 `tool_calls`（工具@服务器、状态、轮次），前端在回答正文前渲染工具调用状态栏（✓ 已执行 / ✕ 被拒 / ⚠ 出错）；每次调用落审计表 `mcp_call_logs`，教师端「最近调用记录」可查。
- 安全边界：令牌只存服务端，任何响应只含 `hasToken` 布尔值；学生一律 403；跨班服务器一律 404；服务器删除后历史审计保留 `server_name`。

配置：`.env` 中 `MCP_AUTH_TOKEN` 为 mcp-demo 服务鉴权令牌（可用 `python -c "import secrets; print(secrets.token_hex(16))"` 生成）；`MCP_MAX_ROUNDS`（默认 3）、`MCP_MAX_CALLS`（默认 5）与超时项可调。

验证路径：教师连接 campus-tools（看到 2 个工具）→ 新建技能（`工具：unit_convert@campus-tools`，不填资料行）并绑定到智能体 → 学生向该智能体提问「3千克等于多少克？」→ 回答正文前出现「✓ 已执行」工具栏 → 教师端调用记录出现 ok 审计行 → 断开服务器后该技能再保存即被拒（未连接）。

### 接口文档（Swagger）

- OpenAPI 描述：`GET /openapi.json`（OpenAPI 3.0.3，覆盖全部接口与错误码）。
- Swagger UI：浏览器打开 `http://localhost:8080/swagger/index.html`，点 Authorize 填入登录返回的 token 即可在线试调。

### 接口自动化测试（apitest/）

`apitest/cases/` 按接口 URL 组织（一个接口一个脚本，`{id}` 段用 `item` 表示，文件名即 HTTP 方法），每个用例断言三层：状态码、响应内容、数据库一致性（容器内直连 db）；`run_all.py` 一键跑完并生成 `apitest/report.html`（已 gitignore，不进仓库）：

```bash
docker compose exec api python apitest/run_all.py
```

覆盖：登录/身份、材料列表、关键字检索、班级提示词读写、技能增改删、智能体列表、新建会话与 SSE 流式提问（含落库核对）、MCP 服务器登记/连接/工具清单/断开与学生提问命中工具的全链路（含审计核对）、作业创建/提交 202/任务落库/重复提交幂等/轮询结果与跨班 404。

## 作业与异步批改（第 8 课）

- **教师**：在仪表盘「作业与异步批改」卡发布作业（标题、题目、参考答案），可查看本班作业列表。
- **学生**：选择作业提交答案 → 接口返回 `202` 与 `taskId`；页面轮询 `GET /api/submissions/<id>`，状态从 `pending → running → succeeded/failed`，完成后展示分数与评语。
- **异步实现**：`jobs` 表即队列（无 Redis/Celery），独立 `worker` 容器（`python -m app.worker`）用 `FOR UPDATE SKIP LOCKED` 领取任务；提交与任务同事务写入，结果与任务状态同事务写回；启动时把超过 60 秒的 `running` 重新入队。
- **幂等**：`submissions` 的 `UNIQUE(assignment_id, student_id)` 与 `jobs.dedupe_key=grade:<submission_id>` 保证重复提交/重投只产生一份结果。

接口（均需 Bearer 令牌）：

```text
POST /api/assignments                             教师创建作业（201）
GET  /api/assignments                             本班作业列表
POST /api/assignments/<id>/submissions            学生提交（202 + taskId）
GET  /api/submissions/<id>                        轮询结果（本人学生或本班教师）
```

验证路径：

```bash
docker compose exec -T api python -m pytest tests/test_grading.py -q   # 正常/失败/边界
docker compose exec -T api python e2e_test.py                          # 含提交→批改→轮询链路
docker compose exec -T api python apitest/run_all.py                   # 含 202、幂等、跨班 404
docker compose exec -T api python scripts/check_security.py           # SEC-05/06
```

worker 可独立停启：停机期间提交仍成功且任务保持 `pending`；启动后自动处理。批改失败按 `max_attempts=3` 重试，最终置 `failed` 并保留可读原因。

## 错题本与错题讲解（第 11 课必做）

- **错题生成**：worker 在 `score < 60` 时与 `finish_submission` 同一事务写入 `wrong_questions`，`UNIQUE(submission_id)` 让重放幂等；question/student_answer/reference_answer 做冗余存储，作业改题不影响历史错题。
- **错题查询**：`GET /api/wrong-questions` 学生返回自己的，教师返回本班全部；`GET /api/wrong-questions/<id>` 跨班/跨他人/不存在一律同构 404。
- **错题讲解**：`POST /api/wrong-questions/<id>/explain` 创建新会话，由 seed 注册的「错题讲解」技能驱动——先诊断错因（概念不清/计算失误/审题偏差/思路方向错误），再分步引导，全程不直接给最终答案。
- **技能清单**：解题引导、作业批改（worker 内部用）、错题讲解三个并列技能，均通过 `agent_skills` 与默认助手多对多绑定，教师可在技能管理页启停。

验证路径：学生提交一道会判错的作业 → worker 批改落库 → `GET /api/wrong-questions` 看到该错题 → `POST /api/wrong-questions/<id>/explain` 拿到 SSE 流 → 模型先点错因再逐步引导。

```bash
docker compose exec -T api python -m pytest tests/test_wrong_questions.py -q
```

## 审计日志（第 9 课）

- **落库而非只打日志**：`audit_logs` 表七列——`action`（操作类型）/ `target_type` + `target_id`（对象）/ `actor_id` / `class_id` / `skill_name`（技能标识）/ `detail`（用量与耗时 JSON）。
- **覆盖范围**：登录/登出、材料上传/重建索引/下载、技能增改删、智能体增改、提示词更新、MCP 服务器登记/更新/删除/连接/断开、作业创建、学生提交、worker 批改（与结果同事务）、错题讲解。
- **查询接口**：`GET /api/audit-logs?limit=50&action=grade&target_type=submission`，教师专用、按班级隔离；未知过滤值 400。
- **教师仪表盘**：新增「🧾 审计日志」卡片，可按操作类型与对象类型过滤查看。
- **故障隔离**：除批改外均为 best-effort，审计写失败只输出 `audit_write_failed`，不影响业务响应。

验证路径：教师登录 → 上传材料 → 发布作业 → 学生提交 → worker 批改 → 打开审计卡片看到 login/create/submit/grade 四类行（grade 行带技能「作业批改」与耗时 ms）。

```bash
docker compose exec -T api python -m pytest tests/test_audit.py -q
```

安全自查与风险记录见 `reports/`：`security-precheck.md`（SEC-01~07 总表）、`risk-authz.md`、`risk-concurrency.md`、`risk-transaction.md`、`security-baseline.md`、`review-01.md`。原两条红项中 SEC-07（审计七列）已在第 9 课转绿，SEC-06（依赖漏洞工具缺失）仍保留。

## 拓展项（第 11 课）

课件列的四项拓展中，「高可用」按 AGENTS.md 不做清单排除（不做多实例/负载均衡），已实现以下两项：

### 技能上传

- `POST /api/skills/import`（教师专用，multipart `file`）：支持 `.md`（单段 source）与 `.json`（`{source}` 或扁平字段），上限 64KB。
- 错误路径：白名单外扩展名 415、超限 413、非 UTF-8 / 解析失败 / 工具引用未登记 400、本班同名 409、学生 403、未登录 401。
- 导入后一律 `enabled=0`，source 规整为单段文本（`启用：否`）；教师在仪表盘点「编辑」改为 `启用：是` 再更新即可上线。
- 审计 `action=create, target_type=skill`，`detail.import=true` 并记原始文件名。

### 关怀式对话

- 内置技能「关怀式对话」默认启用并绑定默认助手，但**仅在学生消息命中挫败/焦虑词表时注入**（`chat.CARE_PATTERNS`：不会/听不懂/好难/崩溃/焦虑/放弃/压力等），普通提问不注入，避免话术污染。
- 关怀轮次即使检索零命中也不返回「资料中未找到」，而是调用模型共情 + 小步引导（`citations` 仍为空，不伪造来源）。
- 教师停用该技能后，关怀注入立即失效。

验证路径：教师选一个 `.md` 技能文件导入 → 列表中看到「启用：否」的新技能 → 编辑改成「启用：是」并更新 → 学生用「这道题我完全不会，好难」提问，回答先共情再给一步小任务。

```bash
docker compose exec -T api python -m pytest tests/test_skill_import.py tests/test_care_skill.py -q
```

## 工程规范与小组项目（第 7 课）

本仓库按「建仓库 → 定规约 → 立规范 → 落骨架」四步工程化，后续每课只在其上做增量交付。

- **常驻约束入口**：[AGENTS.md](AGENTS.md)。任何协作者或编码代理先读它；每条规则都带一行「检查：」说明如何验证。
- **规范明细**：`docs/standards/` 下 8 份——产品设计、后端开发、安全开发、测试、部署运维（必修五类），以及 AI 应用、数据、评审与完成定义（补充三类）。
- **规约**：`openspec/specs/` 为 17 个能力主 spec；能力与场景的对应关系见 `docs/lesson-07/ability-scenarios.md`。
- **变更流程**：每次改动开一条变更，名称为 `YYYY-MM-DD-短横小写英文名`，四份文件齐全并通过 `openspec validate <变更名> --strict`，验收后归档到 `openspec/changes/archive/`。
- **提交信息**：写清「改了什么、依据哪条规约」。
- **骨架基线**：`/health`（存活）+ `/health/ready`（依赖连通）+ 单行 JSON 访问日志（`ts/level/request_id/method/path/status/ms/class_id/user_id`，响应头回显 `X-Request-Id`），标签 `v0.0.1-skeleton`。
- **小组**：1 人独立完成，兼任全部三角色；角色说明与个人贡献记录见 `docs/lesson-07/roles-and-contribution.md`。
- **验证记录**：`docs/lesson-07/verification.md`（含从零启动、三条门禁命令的真实输出）。

提交前门禁：

```bash
docker compose exec -T api python -m pytest -q
docker compose exec -T api python e2e_test.py
docker compose exec -T api python apitest/run_all.py
```

## 数据持久化与重置

- MySQL 数据存放在 named volume `mysql_data`，Qdrant 向量数据存放在 named volume `qdrant_data`，上传文件挂载在宿主机 `./uploads`。
- `docker compose down` 后再 `docker compose up`（**不带** `-v`）：全部账号、会话、材料、切片与向量数据保留。
- `docker compose down -v` 会删除数据卷、清空数据库与向量库（下次启动自动重建并重新预置种子数据），**只能用于主动重置环境**，不能作为常规重启方式。
  注意：`down -v` 不清除 `./uploads` 中已上传的文件，如需彻底重置可手动清空该目录。

## 单实例部署声明

**本迭代仅支持单实例部署。** 上传文件、MySQL 与 Qdrant 数据均存放于单机数据卷、运行状态按单进程设计，未针对多副本/横向扩展做共享存储与状态一致性设计；多副本部署会出现数据与状态不一致，不在支持范围内。限流与生产级高可用（MySQL/Qdrant 主从、多副本负载均衡）均属本学期不做项。

## 运行测试

```bash
# 标准路径：容器内跑（直连内部网络 db/qdrant，无需宿主机端口；网关以离线 fake 替代）
docker compose exec api pytest

# 端到端场景回归（test-client，容器内）
docker compose exec api python e2e_test.py

# 端到端场景回归（HTTP，经 web 入口 8080；未配置网关密钥时向量/问答项按 503 验收）
python e2e_test.py --http

# 接口自动化测试（apitest/，容器内经 Nginx 真链路，生成 apitest/report.html）
docker compose exec api python apitest/run_all.py
```

## 技术栈

Flask + MySQL 8.0（PyMySQL，ngram 全文索引）+ Qdrant 向量库 + OpenAI 兼容模型网关（仅服务端）+ Nginx 反向代理；Docker Compose 六服务编排（web / api / db / qdrant / mcp-demo / worker），仅 web 映射宿主机端口。
