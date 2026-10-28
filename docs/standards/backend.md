# 后端开发规范

适用范围：`app/routes`、`app/services`、`app/repositories`、`app/db`。所有条目以现有代码为基准，新代码照此执行。

## 分层与依赖方向

- 依赖方向固定：`routes` → `services` → `repositories` → `db`；禁止反向依赖与跨层直连。
  检查：`grep -rn "import flask" app/repositories app/services` 无匹配；`grep -rn "app.routes" app/services app/repositories` 无匹配。
- routes 只做 HTTP 边界：解析参数、调服务、组装响应；SQL 只在 `app/repositories/`。
  检查：`grep -rn "SELECT\|INSERT\|UPDATE\|DELETE FROM" app/routes` 无匹配（`methods=["DELETE"]` 不算 SQL）。
- 第三方调用只在 services：`model_gateway.py`（网关）、`mcp_client.py`（MCP 出站）。
  检查：`grep -rn "requests.post\|requests.get" app/` 仅命中这两个文件与 `app/routes/health.py` 的就绪探活。
- 一次请求的数据库连接在路由内 `get_connection` 取得并 `finally` 关闭，不跨请求复用。
  检查：`grep -rn "get_connection" app/routes` 每处均有对应的 `conn.close()`；`tests/test_mcp.py::TestRegistryAPI` 全过。

## 接口命名与版本

- 新增接口一律 `/api/` 前缀 + 资源复数 + `<int:xxx_id>` 路径参数，例如 `/api/mcp/servers/<int:server_id>/connect`。
  检查：`grep -n '@.*_bp.route("/api' app/routes` 逐条符合命名格式。
- 既有对外接口路径不改：`/auth/login`、`/auth/me`、`/materials`、`/search`、`/ask`。
  检查：`grep -rn "@.*_bp.route" app/routes` 与前一条清单比对。
- 不引入 `/v1` 之类 URL 版本段；破坏性变更走 openspec 变更并同步改 `api_docs.py`。
  检查：`grep -c "/v1" app/routes` 为 0；`openspec list --specs` 含对应能力，变更存在时 `openspec validate <变更名> --strict` 通过。
- 列表类查询的条数与分页用 query 参数并夹紧范围（`/api/mcp/call-logs` 的 `limit` 夹在 1–200）。
  检查：`tests/test_mcp.py::TestToolLoop` 与 `app/routes/api_mcp.py::list_call_logs` 的 `max(1, min(limit or 50, 200))` 一致。

## 统一响应与错误码

- 成功：集合用 `{"materials": [...]}` / `{"servers": [...]}`，单体用 `{"server": {...}}` 或扁平对象（如 `GET /materials/<id>`）；创建 201，删除 204。
  检查：`tests/test_mcp.py::TestRegistryAPI::test_create_and_update_and_delete`（201/204/200 三种返回形态）。
- 错误：`{"error": "短语"}`；额外字段只有 503 的 `detail` 与 `connect` 失败的 `status`，`detail` 不含密钥（审计接口里同名字段是调用记录内容，不是错误信息）。
  检查：`grep -rn "\"detail\"" app/routes` 除 schema 与审计字段外只在 503 分支；`grep -rn "\"status\": \"disconnected\"" app/routes/api_mcp.py` 仅连接失败分支。
- 400：参数或业务规则不合法 —— `POST /search` 空 query、`POST /api/conversations` 的 `agent_id` 非整数、技能 source 解析失败、reindex 的 custom 参数越界、`base_url` 不以 http(s) 开头。
  检查：`tests/test_retrieval.py::TestAsk`、`tests/test_assistant.py::TestConversationsAPI::test_message_auth_and_validation`、`tests/test_mcp.py::TestSkillReferenceValidation`。
- 401：无 token、token 过期、`jti` 已撤销 —— 例如不带 `Authorization` 调 `GET /auth/me`。
  检查：`tests/test_auth.py::TestAuthRequired`。
- 403：角色不符 —— 学生 `POST /materials`、学生任一 `/api/mcp/*`、学生 `PUT /api/prompt`。
  检查：`tests/test_role.py::TestRoleRequired`、`tests/test_assistant.py::TestPromptAPI::test_student_put_forbidden`。
- 404：不存在或跨班 —— `GET /materials/<id>` 跨班、他人会话、跨班 MCP 服务器 id、跨班技能 id，响应体与真不存在同构。
  检查：`tests/test_isolation.py::TestCrossClassRejection`、`tests/test_assistant.py::TestConversationsAPI::test_detail_not_owned_or_cross_class_404`。
- 409：唯一约束冲突 —— 同班重复登记 MCP 服务器名（`uq_mcp_servers_class_name`）。
  检查：`tests/test_mcp.py::TestRegistryAPI::test_create_duplicate_409`。
- 413：超过上传上限（`UPLOAD_MAX_SIZE_MB`）；415：扩展名不在 `.txt`/`.md` 白名单（`app/services/upload.py`）。
  检查：`tests/test_materials.py::TestUploadConstraints`。
- 500：仅未预期异常的兜底 —— 上传落库失败 `{"error": "upload failed"}`、重建失败 `{"error": "reindex failed"}`，不回传异常栈或 SQL。
  检查：`grep -n "\"upload failed\"\|\"reindex failed\"" app/routes/materials.py`；`tests/test_materials.py::TestUploadMaterial::test_transaction_failure_leaves_no_orphans`。
- 502：上游工具服务器握手或发现失败 —— `POST /api/mcp/servers/<id>/connect` 返回 502 并把该服务器置 `disconnected`、清空缓存。
  检查：`tests/test_mcp.py::TestRegistryAPI::test_connect_bad_token_502`、`tests/test_mcp.py::TestRegistryAPI::test_connect_replaces_cache_and_disconnect_clears`。
- 503：依赖不可用 —— vector/hybrid 检索、`POST /ask`、SSE 前网关错误（`chat.start` 抛 `AnswerUnavailable`）。
  检查：`tests/test_retrieval.py::TestHybridAndRRF::test_qdrant_unavailable_hybrid_503`、`tests/test_assistant.py::TestConversationsAPI`。

## 参数校验位置

- routes 层只校验存在性、类型、必填与格式：int id、非空字符串、`http://`/`https://` 前缀、`agent_id` 必须是 `int`。
  检查：`app/routes/materials.py`、`app/routes/api_conversations.py::create_conversation`、`app/routes/api_mcp.py::_parse_server_body`。
- services 层校验业务规则：切片长度 100–2000 与重叠 0–50%、文件白名单与大小、技能工具四查、工具参数按 `inputSchema` 校验。
  检查：`tests/test_chunking.py::TestCustomStrategy`、`tests/test_mcp.py::TestReferenceAndSanitize`。
- 请求体中的 `class_id`、`role`、`system` 消息一律丢弃，不参与任何决策。
  检查：`tests/test_retrieval.py::TestSearchClassIsolation`（伪造班级无效）、`tests/test_retrieval.py::TestAsk`（客户端 system 消息被丢弃）。

## 事务与外部调用

- 上传：文件先落盘，随后 `materials` 与 `knowledge_entries` 在同一事务写入；事务失败回滚并删除已落盘文件；提交成功后才切分与嵌入，索引失败只把切片标 `embedding_status=failed`。
  检查：`tests/test_materials.py::TestUploadMaterial::test_transaction_failure_leaves_no_orphans`、`tests/test_retrieval.py::TestUploadIndexingFailure`。
- 事务里不发起外部调用：模型嵌入、MCP `tools/call` 都在提交/读取之后独立执行。
  检查：`app/services/upload.py` 的 `conn.commit()` 之后才调 `index_material`；`tests/test_retrieval.py::TestUploadIndexingFailure`。
- 工具审计每次调用即时提交一行，SSE 正文与用户消息只在发 `done` 前一次性落库。
  检查：`app/services/chat.py::_execute_call` 与 `_persist`；`tests/test_mcp.py::TestToolLoop`。

## 幂等声明

- `PUT /api/prompt` 是整体替换且空值非法：`body` 去空白后必须非空，否则 400；保存值即下一次生成生效的全部班级提示词。
  检查：`tests/test_assistant.py::TestPromptAPI::test_teacher_put_then_get`、`tests/test_assistant.py::TestPromptAPI::test_put_empty_body_400`。
- `PUT /api/mcp/servers/<id>` 是部分更新：`token` 传空串表示清除，不传表示保持不变；任何更新都会清空工具缓存并置 `disconnected`。
  检查：`tests/test_mcp.py::TestRegistryAPI::test_create_and_update_and_delete`；`app/repositories/mcp.py::update` 的注释与实现一致。
- `connect` / `disconnect` 可重复调用：重复连接整体替换清单，重复断开仍返回 200 且缓存为空。
  检查：`docker compose exec -T api python -m pytest tests/test_mcp.py::TestRegistryAPI -q` 通过（含重复连接与重复断开的用例）。

## 配置外置与失败策略

- 所有参数在 `app/config.py` 集中声明；必填项 `DB_NAME`、`DB_USER`、`DB_PASSWORD`、`SESSION_TTL_HOURS`、`JWT_SECRET` 缺失即 `ConfigError`，`run.py` 退出码 1。
  检查：`docker compose run --rm -e JWT_SECRET= api python run.py` 退出码 1。
- 构建/测试用的调参走环境变量（如 `RETRIEVAL_VECTOR_THRESHOLD`、`MCP_MAX_CALLS`），不在代码里改默认值。
  检查：`grep -rn "MCP_MAX\|RRF_K\|ASK_TOP_K" app/` 只出现在 `app/config.py` 与使用处读取，无硬编码常量。

## 排序与唯一兜底键

- 排序必须落到唯一键：`materials` 用 `created_at DESC, id DESC`，会话用 `updated_at DESC, id DESC`，审计与技能/智能体按 `id`，切片按 `chunk_index`（材料内唯一）。
  检查：`grep -rn "ORDER BY" app/repositories` 每条末尾为 `id`、`chunk_index`、`skill_id` 或 `material_id` 之一，无仅按时间排序的语句。
