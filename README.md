## 价值

为校园教学提供最小可用的身份认证、角色权限、班级数据隔离、知识库材料管理闭环、限定班级范围且可溯源的知识库检索问答、教师可配置且流式输出的「解题助手」智能体，以及可登记外部 MCP 工具服务器、由宿主代为执行工具调用的智能体能力，作为后续教学功能的安全底座。

## 场景

教师向本班知识库投放教学材料，并配置班级提示词、「解题引导」技能与智能体（绑定技能/材料/工具）；学生可在本班材料中按关键字/语义检索具体切片、查看出处并打开原文件，可以就本班材料提问，也可以在解题助手会话中逐步获得引导式回答——回答以 SSE 流式逐字输出，先展示引用出处与工具调用状态，无依据时明确告知而不编造。

## 本学期不做

作业提交与批改、异步任务队列、SSO/生产高可用、MCP resources/prompts 能力与第三方 MCP SDK 接入、技能真实工具执行与智能匹配。

## 快速开始（Docker Compose，唯一交付形态）

前置要求：仅安装 Docker Desktop（含 Docker Compose v2），无需 Python/MySQL 本机环境。

```bash
# 1. 准备环境变量（填写数据库密码等必填项）
cp .env.example .env
#    编辑 .env：DB_PASSWORD、DB_ROOT_PASSWORD、JWT_SECRET 必须改成你自己的值
#    （JWT_SECRET 可用 python -c "import secrets; print(secrets.token_hex(32))" 生成）
#    使用向量检索/问答还需填写 EMBED_API_KEY/EMBED_MODEL 与 CHAT_API_KEY/CHAT_MODEL

# 2. 一键构建并启动（web / api / db / qdrant / mcp-demo 五服务）
docker compose up --build -d

# 3. 查看服务状态（五个服务均应为 running）
docker compose ps

# 4. 验证
#    健康检查：http://localhost:8080/health → {"status":"ok"}
#    登录页：  http://localhost:8080/login
```

> web 服务是唯一映射宿主机端口的入口（默认 8080，由 `.env` 的 `WEB_PORT` 控制）；
> api、MySQL 与 Qdrant 均只在 Compose 内部网络，宿主机无法直连。
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
- 无命中时返回固定文案「资料中未找到相关内容」且不调用模型；会话归属班级+用户双校验，跨班一律 404。
- 历史多轮：服务端自动携带最近 6 轮对话；流式中断时不落库，前端提示「（回答中断）」。

## MCP 工具服务（第 6 课）

教师可在「🔌 MCP 工具服务」卡登记外部 MCP 服务器（JSON-RPC 2.0 单端点，Streamable HTTP 传输，Bearer 令牌鉴权），连接后服务端缓存其工具清单（`initialize` / `tools/list`），学生提问命中带工具引用的技能时由宿主（api）代为执行工具调用（`tools/call`）：

- 同仓库 `mcp-server/` 内置演示服务器（campus-tools：`formula_hint` 公式/步骤提示、`unit_convert` 单位换算），首次启动自动预登记到各班（不自动连接），令牌取 `.env` 的 `MCP_AUTH_TOKEN`，未配置则跳过预登记。
- 技能 source 的「工具：」行支持 `工具名@服务器名` 引用（如 `unit_convert@campus-tools`），保存时四查校验（格式/已登记/已连接/在最近发现清单内），不合法即 400 可读错误。
- 工具调用循环：模型提出调用（OpenAI tools 协议）→ api 校验参数并携带该服务器令牌执行 → 结果经指令式句式安全检查后作为数据拼回上下文 → 最多 3 轮、累计 5 次，超限优雅降级为普通回答。
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

覆盖：登录/身份、材料列表、关键字检索、班级提示词读写、技能增改删、智能体列表、新建会话与 SSE 流式提问（含落库核对）、MCP 服务器登记/连接/工具清单/断开与学生提问命中工具的全链路（含审计核对）。

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

Flask + MySQL 8.0（PyMySQL，ngram 全文索引）+ Qdrant 向量库 + OpenAI 兼容模型网关（仅服务端）+ Nginx 反向代理；Docker Compose 五服务编排（web / api / db / qdrant / mcp-demo），仅 web 映射宿主机端口。
