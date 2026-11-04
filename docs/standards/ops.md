# 部署运维规范

适用范围：构建、启动、健康检查、日志、发布回滚、数据变更与备份。单实例、本地 Compose 交付。

## 可复现构建

- 基镜像固定标签：`python:3.12-slim`、`mysql:8.0`、`qdrant/qdrant:v1.12.1`、`nginx:alpine`、mcp-server 同用 `python:3.12-slim`；不使用 `latest`。
  检查：`grep -n "FROM\|image:" Dockerfile mcp-server/Dockerfile docker-compose.yml` 无 `latest`。
- 依赖只在 `requirements.txt`（上下界）与 `mcp-server/requirements.txt`（`==` 固定）声明；禁止进容器临时安装。
  检查：`grep -c "==" mcp-server/requirements.txt` 等于其行数；`docker compose exec -T api pip check`；`git diff --stat requirements.txt mcp-server/requirements.txt`。
- 构建产物不包含 `.env`（`.dockerignore` 已排除）；上传文件与运行数据在运行时走卷挂载（`./uploads`），镜像只承载代码。
  检查：`grep -n "^\.env" .dockerignore`；`git check-ignore -v .env uploads` 有输出；`docker compose build --no-cache` 成功。

## 环境分级

- 两级：本地开发（`.env` + 六服务 + 业务库 `campusclaw`）与测试（`campusclaw_test` 库 + `campusclaw_chunks_test` collection + 离线 fake 网关）。
  检查：`docker compose config` 中 api 服务的 `TEST_DB_NAME`、`TEST_QDRANT_HOST`；`grep -n "campusclaw_chunks_test" tests/conftest.py`。
- 没有预发与生产环境；"发布"即本机 `docker compose up --build -d`，不要按多环境参数化。
  检查：`docker compose ps` 六服务 running；`openspec/specs/app-runtime/spec.md` 的编排定义。
- 测试与开发共用 db 容器但库名、collection 名必须不同，禁止跨用。
  检查：`docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SHOW DATABASES"'` 中存在 `campusclaw` 与 `campusclaw_test` 两个独立库。

## 健康检查

- `GET /health` 只报进程存活，恒 200，不探数据库，不因依赖抖动被判不健康。
  检查：`curl http://localhost:8080/health` 返回 `{"status":"ok"}`；`tests/test_health_ready.py::test_liveness_is_plain_ok`。
- `GET /health/ready` 同时探 db 与 qdrant；qdrant 用 `PROBE_TIMEOUT_SECONDS=2.0`，db 用连接自身超时；任一不可达返回 503、`status=degraded`、逐项给 `checks`。
  检查：`grep -n "PROBE_TIMEOUT_SECONDS" app/routes/health.py` 为 2.0；`curl -i http://localhost:8080/health/ready`；`tests/test_health_ready.py::test_readiness_reports_each_dependency`。
- 依赖未就绪不得阻塞启动：Qdrant 与网关缺失时 api 仍启动，关键字检索立即可用。
  检查：`docker compose stop qdrant && curl -X POST http://localhost:8080/search -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"query":"阅读材料","mode":"keyword"}'` 返回 200。

## 停机语义

- api 无优雅排空：容器收 SIGTERM 直接结束进程；未发出 `done` 的回答不落库，前端显示「（回答中断）」。
  检查：`grep -n "（回答中断）" app/routes/pages.py`；`grep -n "_persist" app/services/chat.py` 只出现在 `done` 分支；`tests/test_assistant.py::TestConversationsAPI::test_sse_hit_flow`。
- 工具调用审计按每次调用即时提交，停机不回滚已完成的调用记录。
  检查：`docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" campusclaw -e "SELECT COUNT(*) FROM mcp_call_logs"'` 重启前后数值不减少；`tests/test_mcp.py::TestToolLoop`。
- 重启前先确认无进行中的 SSE 提问（对话区不应处于「思考中...」），避免半截回答被误认为成功。
  检查：`docker compose logs api --tail 20` 中无未结束请求时再执行 `docker compose restart api`；重启后 `messages` 表行数不变。
- worker 可独立停止与启动：停机期间提交仍返回 202 且任务保持 `pending`；启动后超时 60 秒的 `running` 任务自动回到 `pending` 再处理，结果只写一次。
  检查：`docker compose stop worker` 后提交 → `jobs.status='pending'`；`docker compose start worker` 后 90 秒内提交转 `succeeded`/`failed`；`tests/test_grading.py::TestWorker::test_stale_running_job_is_requeued`。

## 日志

- 每请求一行 JSON 到 stdout，字段固定：`ts`、`level`、`request_id`、`method`、`path`、`status`、`ms`、`class_id`、`user_id`。
  检查：`docker compose logs api --tail 5` 每行可 `json.loads`；`tests/test_health_ready.py::test_request_id_is_echoed_and_logged`。
- `X-Request-Id` 回显：入站带则复用，不带则生成，便于把用户报障定位到单行日志。
  检查：`curl -i -H "X-Request-Id: trace-demo" http://localhost:8080/health` 响应头含同值，日志同值。
- 日志不得含密码、token、网关密钥、材料正文。
  检查：`tests/test_auth.py::TestNoPlaintextLogs`；`docker compose logs api | grep -i "bearer\|password_hash"` 无匹配。
- worker 同样单行 JSON 到 stdout，至少含 `event`、`jobId`、`submissionId`、`status`；不得输出学生答案正文或参考答案。
  检查：`docker compose logs worker --tail 5` 每行可 `json.loads` 且无答案文本；`grep -n "answer" app/worker.py` 只在取数处，不进入日志。

## 发布与回滚

- 发布步骤固定：`git pull` → `docker compose up --build -d` → `docker compose ps` → `curl /health` → 跑三条测试命令。
  检查：`docker compose ps` 六服务 running；`curl http://localhost:8080/health`。
- 回滚：`git checkout <上一个门禁全绿的提交>` → `docker compose up --build -d`；不使用镜像仓库与蓝绿。
  检查：`git log --oneline -3` 确认目标提交；回滚后 `docker compose exec -T api python -m pytest -q` 通过。
- 发布不做数据回滚；如本次含迁移，先按下一节备份再发。
  检查：`ls -1t backup-*.sql uploads-*.tgz | head -2` 文件时间戳早于当次 `docker compose up --build -d`。

## 数据变更顺序

- 顺序：备份 → 迁移（只增）→ `up --build -d` → 校验 `/health/ready` 与登录 → 再放流量给教师使用。
  检查：`docker compose exec -T db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" campusclaw' > backup.sql` 成功且文件非空；随后 `docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" campusclaw -e "SHOW TABLES"'` 含全部表。
- 迁移文件只允许新增文件与 `CREATE TABLE IF NOT EXISTS` 语句，不改既有列定义、不写 `DROP`。
  检查：`grep -rn "DROP \|ALTER TABLE" migrations/` 无匹配；`git diff --stat migrations/` 只新增文件。
- 新迁移必须同时登记到 `app/__init__.py`、`tests/conftest.py`、`seeds/seed.py` 三处 MIGRATIONS。
  检查：`grep -c '\.sql"' app/__init__.py tests/conftest.py seeds/seed.py` 三处均为 6（同批登记同一份清单）。

## 备份与恢复

- 备份对象四件：`mysql_data`（`mysqldump`）、`qdrant_data`（停服后复制卷或 `qdrant` 快照）、`./uploads` 目录、`.env` 离线副本。
  检查：`docker volume ls | grep -E "mysql_data|qdrant_data"`；`ls uploads/materials` 非空。
- 目标：RPO 24 小时（每日一次全量），RTO 30 分钟（重建容器 + 恢复备份）。
  检查：备份目录存在最近 24 小时内文件；按恢复步骤演练后 `SELECT COUNT(*) FROM materials` 与备份前一致。
- 恢复后必做三项验收：预置账号可登录、材料可下载、本班检索有命中。
  检查：`curl -X POST http://localhost:8080/auth/login -H "Content-Type: application/json" -d '{"username":"teacher_a","password":"teacher_a_pass"}'` 返回 200；`tests/test_materials.py::TestDownload`；`POST /search` 命中种子材料。
- `down -v` 只用于主动重置，不用于常规重启；它也不清 `./uploads`。
  检查：`docker compose down && docker compose up -d` 后数据仍在（README「数据持久化与重置」）。

## 单实例与容量

- 仅支持单实例部署：上传文件落在宿主机 `./uploads` 目录、运行状态在单进程内存，不做多副本、共享存储与负载均衡。
  检查：`docker compose config --services` 六服务各一实例；README「单实例部署声明」。
- 不做应用层限流；容量靠固定配额控制：`SEARCH_PATH_LIMIT=20`、`SEARCH_FINAL_LIMIT=10`、`ASK_TOP_K=4`、`EXCERPT_LIMIT=200`、`limit` 1–200。
  检查：`grep -n "SEARCH_PATH_LIMIT\|SEARCH_FINAL_LIMIT\|ASK_TOP_K\|EXCERPT_LIMIT" .env.example`。
- 超时基线：网关 5s 连接 / 30s 读；MCP 3s 连接 / 15s 读；qdrant 就绪探活 2s（db 探活走连接超时，不设单独常量）。
  检查：`grep -n "GATEWAY_TIMEOUT_CONNECT\|GATEWAY_TIMEOUT_READ\|MCP_TIMEOUT_CONNECT\|MCP_TIMEOUT_READ" app/config.py` 默认 5/30、3/15；`grep -n "PROBE_TIMEOUT_SECONDS" app/routes/health.py` 为 2.0。
