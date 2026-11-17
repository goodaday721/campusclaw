# AGENTS.md

本文件是 Harness 常驻约束入口：任何在本仓库工作的代理或协作者，先读本文件，再按 `docs/standards/` 的明细执行。

## 1. 技术栈与硬性约束

- 运行形态只有一种：`docker compose up --build -d` 拉起 web / api / db / qdrant / mcp-demo / worker 六服务，不提供本机直跑路径。
  检查：`docker compose config --services` 输出恰为 web、api、db、qdrant、mcp-demo、worker。
- 只有 web（Nginx）映射宿主机端口（`${WEB_PORT:-8080}:80`）；api / db / qdrant / mcp-demo / worker 一律不映射。
  检查：`docker compose config` 中 `ports` 只出现在 web 段。
- 依赖只在根 `requirements.txt`（上下界）与 `mcp-server/requirements.txt`（`==` 固定版本）声明；禁止在容器内临时 pip 安装。
  检查：`docker compose exec -T api pip check` 无冲突；`git diff --stat requirements.txt mcp-server/requirements.txt`。
- 数据库变更只经 `migrations/00N_*.sql`，并在 `app/__init__.py`、`tests/conftest.py`、`seeds/seed.py` 三处 MIGRATIONS 同步登记。
  检查：`grep -c "006_grading.sql" app/__init__.py tests/conftest.py seeds/seed.py` 三处均为 1。
- 配置一律经 `app/config.py` 从环境变量读取：必填缺失即启动失败，可选缺失走降级。
  检查：`docker compose run --rm -e DB_NAME= api python run.py` 退出码 1，stderr 含 `Startup error: Missing required environment variable: DB_NAME`。

明细：`docs/standards/ops.md`

## 2. 分层与依赖方向

- 依赖方向固定：`app/routes` → `app/services` → `app/repositories` → `app/db`；不得反向、不得跨层直连。
  检查：`grep -rn "import flask" app/repositories app/services` 无匹配；`grep -rn "app.routes" app/services app/repositories` 无匹配。
- routes 只做 HTTP 边界（取参数、调服务、组响应），不写 SQL。
  检查：`grep -rn "SELECT\|INSERT\|UPDATE\|DELETE FROM" app/routes` 无匹配。
- 第三方调用只出现在 services：模型网关在 `app/services/model_gateway.py`，MCP 出站在 `app/services/mcp_client.py`。
  检查：`grep -rn "requests.post\|requests.get" app/` 仅命中这两个文件与 `app/routes/health.py` 的就绪探活。
- 新表必须配套 `app/repositories/` 下的同名模块，SQL 全参数化；按 id 的资源读取必须走带作用域的 `find_by_id_scoped_to_class` / `find_owned` / `mcp.find` / `grading.find_*`。
  检查：`grep -rn "find_owned\|find_by_id_scoped_to_class\|mcp.find(\|grading.find" app/routes` 覆盖全部按 id 读取；`grep -rn "conversations.find_by_id(" app/` 无匹配。

## 3. 接口与响应约定

- 新增接口用 `/api/` 前缀 + 资源复数 + `<int:xxx_id>` 路径参数（参照 `/api/mcp/servers/<int:server_id>`）。
  检查：`grep -n "@.*_bp.route(\"/api" app/routes` 逐条符合 `/api/<复数>` 与 `<int:...>` 格式。
- 成功响应是 JSON 对象：集合 `{"<资源复数>": [...]}`，单体 `{"<资源>": {...}}` 或扁平对象（如 `GET /materials/<id>`）。
  检查：`tests/test_mcp.py::TestRegistryAPI::test_create_and_update_and_delete`（`{"server":...}` 201/200、204 删除）、`tests/test_materials.py::TestListMaterials`（`{"materials":[...]}`）。
- 错误响应统一 `{"error": "..."}`；额外字段只有 503 的 `detail` 与连接失败的 `status`；状态码用 200/201/204/400/401/403/404/409/413/415/500/502/503，500 仅作未预期异常兜底且文案不可含内部细节。
  检查：`grep -rn "\"detail\"" app/routes` 除 `api_docs.py` 的 schema 与 `api_mcp.py` 的审计字段外，只出现在 `search.py`、`ask.py`、`api_conversations.py` 的 503 分支。
- 跨班资源与不存在资源返回同构 404，不得用 403 暗示资源存在。
  检查：`tests/test_materials.py::TestDownload::test_cross_class_download_isomorphic_404`、`tests/test_isolation.py::TestCrossClassRejection`。
- 每个 JSON 业务接口（`/auth/*`、`/materials*`、`/search`、`/ask`、`/api/*`）必须在 `app/routes/api_docs.py` 的 `/openapi.json` 中同步描述；页面路由、Swagger 页面与探活端点 `/health/ready` 除外。
  检查：`docker compose exec -T api python -c "import json,urllib.request;print(sorted(json.load(urllib.request.urlopen('http://localhost:5000/openapi.json'))['paths']))"` 输出包含上述业务路由且无缺失。

明细：`docs/standards/backend.md`

## 4. 安全底线

- 身份只来自 `Authorization: Bearer <JWT>` 加 `sessions` 表校验；payload 只含 sub/jti/iat/exp，角色与班级每请求从 `users` 表实时读取。
  检查：`docker compose exec -T api python -m pytest tests/test_auth.py::TestAuthRequired -q` 通过（含篡改 payload 与逐请求读库两个用例）。
- 每个受保护端点挂 `@auth_required`；教师专属写操作再挂 `@role_required("teacher")`，学生越权一律 403；学生可写的只有会话、消息与本人作业提交（归属校验，无角色装饰器，提交端点显式拒绝非学生）。
  检查：`grep -rn "@role_required" app/routes` 与 `grep -rn "@.*_bp.route(\"/api/conversations" app/routes` 对照，其余写路由均有角色装饰器；`tests/test_role.py::TestRoleRequired`。
- 按 id 的读写必须带 `class_id` 条件；跨班一律 404。
  检查：`tests/test_isolation.py::TestDirectURLBypass`、`tests/test_assistant.py::TestConversationsAPI::test_detail_not_owned_or_cross_class_404`。
- 密钥（`JWT_SECRET`、`DB_PASSWORD`、`MCP_AUTH_TOKEN`、网关 key）只在本地 `.env`，不进代码、日志、响应。
  检查：`tests/test_auth.py::TestNoPlaintextLogs`、`tests/test_mcp.py::TestRegistryAPI::test_seed_registered_has_token_only`。
- 页面把服务端数据（文件名、摘录、回答、工具文本）写入 `innerHTML` 前必须经同文件内的 `escapeHtml`。
  检查：`grep -n "innerHTML" app/routes/pages.py` 每处拼接变量都出现 `escapeHtml`。

明细：`docs/standards/security.md`

## 5. 测试与验收门禁

- 任何行为改动须同时带用例，覆盖正常、失败、边界三类；无用例的改动不合并。
  检查：`docker compose exec -T api python -m pytest tests/test_materials.py -q` 通过（`TestUploadMaterial` 正常、`TestUploadConstraints` 失败与边界）。
- 提交前三条命令必须全绿：pytest、e2e、apitest。
  检查：`docker compose exec -T api python -m pytest -q`、`docker compose exec -T api python e2e_test.py`、`docker compose exec -T api python apitest/run_all.py` 退出码均为 0。
- 测试只连隔离资源：库 `campusclaw_test`、向量 collection `campusclaw_chunks_test`；禁止指向业务库。
  检查：`grep -n "campusclaw_test\|campusclaw_chunks_test" tests/conftest.py`；`docker compose config` 中 api 带 `TEST_DB_NAME`。
- 不得用 `skip` / `xfail` 掩盖失败；确需跳过的必须在评审记录写明原因与补救项。
  检查：`docker compose exec -T api python -m pytest -q -rs` 输出无 skip 条目。

明细：`docs/standards/testing.md`

## 6. 部署交付

- 交付物是 compose 加 `.env.example`；首次启动自动迁移、种子、切片回填，无需手工初始化。
  检查：`docker compose up --build -d` 后 `docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" campusclaw -e "SHOW TABLES"'` 列出全部 21 张表，且 `SELECT COUNT(*) FROM users` 为 4。
- `/health` 只报存活（恒 200，不探依赖）；`/health/ready` 探 db 与 qdrant，任一不可用返回 503。
  检查：`curl http://localhost:8080/health`、`curl -i http://localhost:8080/health/ready`、`tests/test_health_ready.py`。
- 数据落在 named volume `mysql_data`、`qdrant_data` 与宿主机 `./uploads`；`down -v` 只用于主动重置。
  检查：`docker volume ls | grep -E "mysql_data|qdrant_data"`；`docker compose down && docker compose up -d` 后数据仍在。
- 仅支持单实例：不做多副本、共享存储与负载均衡。
  检查：`docker compose config --services` 为六服务各一实例；`docker compose ps` 六服务 running。

明细：`docs/standards/ops.md`

## 7. AI 与 MCP 调用边界

- 嵌入与对话只经 `app/services/model_gateway.py` 在服务端调用；浏览器拿不到网关地址与密钥。
  检查：`grep -rn "CHAT_API_KEY\|EMBED_API_KEY" app/routes` 无匹配。
- 零命中固定返回「资料中未找到相关内容」且 `citations` 为空，不调用模型。
  检查：`tests/test_retrieval.py::TestAsk::test_no_evidence_does_not_call_chat`、`tests/test_retrieval.py::TestKeywordSearch::test_no_match_returns_fixed_message`。
- 检索班级只取会话 `classId`；默认 hybrid，RRF k=60，向量阈值 0.35。
  检查：`tests/test_retrieval.py::TestSearchClassIsolation::test_forged_body_class_id_ignored`；`grep -n "0.35\|RRF_K" .env.example`。
- MCP 工具只能经技能 `工具：` 行的 `工具名@服务器名` 引用，保存时四查（格式/已登记/已连接/在清单内）全过才允许。
  检查：`docker compose exec -T api python -m pytest tests/test_mcp.py::TestSkillReferenceValidation -q` 通过（格式/未连接/连接后三个用例）。
- 工具返回按数据处理；命中指令式句式整条丢弃；每问上限 3 轮、累计 5 次。
  检查：`tests/test_mcp.py::TestReferenceAndSanitize::test_sanitize_tool_text`、`tests/test_mcp.py::TestToolLoop::test_round_and_total_caps`。

明细：`docs/standards/ai.md`

## 8. 文档与变更流程

- 行为变更先落 openspec change（proposal / design / tasks / specs），再动代码；完成后归档到 `openspec/changes/archive/<日期>-<变更名>/`，能力变更合并回 `openspec/specs/`。
  检查：`openspec list` 输出 `No active changes found.`；`openspec list --specs` 列出 17 个能力 spec。
- README 必须同步能力、启动命令与验证路径；新增页面或接口要写进验证路径。
  检查：`git diff --stat README.md`；`grep -n "验证" README.md`。
- `docs/standards/` 的明细与代码同批更新，不允许只改代码不改规范。
  检查：`openspec validate --all --strict --no-interactive` 输出 `0 failed`；`openspec list --specs` 可列出全部能力 spec。

明细：`docs/standards/review.md`

## 不做清单（本学期）

- 不做 MCP resources / prompts 能力，不做 stdio 传输，不引入第三方 MCP SDK。
  检查：`grep -ri "resources/list\|prompts/list\|stdio\|mcp-sdk" app/ mcp-server/ requirements.txt` 无匹配。
- 不做多实例部署、SSO、生产级高可用，也不做应用层限流。
  检查：`docker compose config --services` 仍为六服务；`grep -rn "rate_limit\|throttle" app/` 无匹配。
- 异步批改只经 `jobs` 表 + `worker` 容器：提交与任务同事务、结果与任务状态同事务、幂等键 `grade:<submission_id>`；`worker` 以 `FOR UPDATE SKIP LOCKED` 领取，启动时把超过 60 秒的 `running` 重新入队；批改结果只写一次。
  检查：`tests/test_grading.py::TestWorker`（成功、重试、重放、空闲）、`tests/test_grading.py::TestSubmissionsAPI::test_resubmit_is_idempotent`。
- 不做技能的智能匹配，不做内置工具之外的自动执行。
  检查：`tests/test_mcp.py::TestReferenceAndSanitize::test_parse_reference`、`tests/test_mcp.py::TestToolLoop::test_hallucinated_tool_not_attributed`。

明细：`docs/standards/{product,backend,security,testing,ops,ai,data,review}.md`
