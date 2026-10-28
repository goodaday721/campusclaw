# 数据规范

适用范围：`migrations/`、`seeds/`、`app/repositories/`、Qdrant 向量库与 `uploads/` 文件。MySQL 8.0，字符集 utf8mb4。

## 命名与审计字段

- 表名、列名一律 snake_case；索引名 `idx_<域>_<列…>`、唯一键 `uq_<表>_<列…>`、外键 `fk_<表>_<目标>`（如 `idx_mcp_logs_class_time`、`uq_mcp_servers_class_name`、`fk_mcp_servers_class`）；既有 `idx_class_status` 保留不改。
  检查：`grep -rn "KEY idx_\|UNIQUE KEY uq_\|CONSTRAINT fk_" migrations/` 每行前缀正确，新增项按上例命名。
- 新建表必须有 `created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP`；既有例外（`classes`、`users`、`sessions`、`knowledge_entries`、`class_prompts`、`agent_skills`、`agent_materials`、`mcp_tools_cache`）只能靠新迁移补列，不得改老迁移文件。
  检查：`grep -h "CREATE TABLE" migrations/*.sql` 列出全部表名；新增表名同时能在 `grep -n "created_at" migrations/<新文件>` 命中。
- 可编辑实体必须有 `updated_at ... ON UPDATE CURRENT_TIMESTAMP`：`skills`、`agents`、`conversations`、`mcp_servers`、`class_prompts`；只追加的流水与关联表不设 `updated_at`。
  检查：`grep -n "updated_at" migrations/004_assistant.sql migrations/005_mcp.sql` 覆盖上述五表，`mcp_call_logs`、`messages` 不出现。
- `mcp_call_logs` 必须能回答五问：谁（`user_id`）、哪个班（`class_id`）、调了什么（`tool_name` + `server_name`）、结果如何（`status` ok/denied/error + `detail`）、哪次会话第几轮（`conversation_id` + `round_no`），再加 `created_at`。
  检查：`tests/test_mcp.py::TestToolLoop::test_hit_with_tool_call` 与 `test_denied_when_disconnected_between_prepare_and_call` 的审计行断言。
- 外键必须声明删除行为：业务数据随班级级联（`ON DELETE CASCADE`），`mcp_call_logs.server_id` 用 `ON DELETE SET NULL` 保留审计；既有未声明的五个（`users.class_id`、`materials.class_id`、`materials.uploader_user_id`、`knowledge_entries.class_id`、`knowledge_chunks.class_id`）保留不改，真要删班需先补迁移。
  检查：`grep -n "ON DELETE" migrations/005_mcp.sql`；`grep -n "fk_chunks_class" -A1 migrations/003_knowledge_chunks.sql` 显示无 `ON DELETE`；`grep -n "fk_materials_uploader" migrations/001_initial_schema.sql` 同样无。

## 迁移

- 迁移只增：只新增 `00N_*.sql`，不改既有文件、不用 `DROP`/`ALTER`（MySQL 8.0 无 `CREATE INDEX IF NOT EXISTS`，索引用内联声明保证幂等）。
  检查：`grep -rn "DROP \|ALTER TABLE" migrations/` 无匹配；`git diff --stat migrations/` 只显示新增文件。
- 新迁移在 `app/__init__.py`、`tests/conftest.py`、`seeds/seed.py` 三处 `MIGRATIONS` 同步登记，顺序与文件名一致。
  检查：`grep -c "005_mcp.sql" app/__init__.py tests/conftest.py seeds/seed.py` 三处均为 1。
- 迁移与种子必须可重复执行：重复启动不产生重复行。
  检查：`tests/test_health.py::TestSeedIdempotent::test_repeated_startup_no_duplicate_seed`。

## 敏感数据分级

- L1 密钥：`users.password_hash`、`sessions.id`（会话 jti）、`mcp_servers.token`，以及 `.env` 里的 `JWT_SECRET`/`MCP_AUTH_TOKEN`/网关 key。永不进接口响应、永不进日志，响应只给 `hasToken`。
  检查：`tests/test_mcp.py::TestRegistryAPI::test_seed_registered_has_token_only`、`tests/test_auth.py::TestNoPlaintextLogs`。
- L2 个人标识：`users.username`、`materials.uploader_user_id`。当前项目无手机号/邮箱字段，新增任何联系方式字段前必须先在本文件登记分级与展示规则。
  检查：`grep -n "username\|uploader_user_id" migrations/001_initial_schema.sql`；`grep -rni "phone\|email\|mobile" migrations/` 无匹配。
- L3 教学数据：材料正文（`knowledge_entries.content`、`knowledge_chunks.chunk_text`）、会话与消息、工具调用记录。仅本班可见，跨班一律 404。
  检查：`tests/test_isolation.py::TestCrossClassRejection`、`tests/test_assistant.py::TestConversationsAPI::test_cross_class_message_404`。
- 不存成绩：本项目不做作业提交与批改，任何"分数/评语/排名"字段一律不引入。
  检查：`grep -rni "score\|grade\|rank" migrations/` 无匹配。

## 向量库与副本

- 向量库只存向量 + 标识（`class_id`、`material_id`、`chunk_id`、`chunk_index`），正文只留在 MySQL。
  检查：`tests/test_retrieval.py::TestVectorPayload::test_qdrant_payload_has_no_text`。
- 切片正文与 `char_start`/`char_end` 必须自洽，区间可回切原文（区间相对预处理后的文本）。
  检查：`tests/test_chunking.py::TestAutoStrategy::test_offsets_slice_back_to_chunk_text`、`tests/test_chunking.py::TestCustomStrategy::test_offsets_relative_to_preprocessed_text`。
- 一份数据有四处副本，删除必须全部覆盖：业务库行（`materials`、`knowledge_entries`、`knowledge_chunks`）、Qdrant 向量、`uploads/materials/<class_id>/<uuid>.<ext>` 文件、派生缓存（`mcp_tools_cache`）；备份另行到期淘汰。
  检查：`ls uploads/materials`；`grep -rn "def delete" app/repositories/` 目前只有 `chunks.delete_by_material`、`skills.delete`、`mcp.delete`、`sessions.delete`，新增材料删除须同时清三表与对应向量。
- 缓存类数据（`mcp_tools_cache`）只保存最近一次成功发现的清单，连接时整体替换、断开或失败时清空。
  检查：`tests/test_mcp.py::TestRegistryAPI::test_create_and_update_and_delete`。

## 双状态：index_status 与 embedding_status

- `knowledge_chunks.index_status` 表示正文可被 MySQL 全文检索，行写入即为 `ready`，与向量无关；现有代码从不写 `failed`（该枚举值仅保留），不得据此判定向量可用性。
  检查：`grep -n "index_status" migrations/003_knowledge_chunks.sql app/services/indexing.py` 写入值只有 `ready`。
- `knowledge_chunks.embedding_status`（`pending`/`ready`/`failed`）表示向量索引状态；嵌入失败置 `failed` 且不写部分向量，正文与关键字检索仍可用。
  检查：`tests/test_retrieval.py::TestUploadIndexingFailure::test_embed_failure_keeps_material_keyword_still_works`。
- 两状态互不推断：不得用 `index_status` 判定能否向量检索，也不得用 `embedding_status` 判定能否关键字检索。
  检查：`grep -n "embedding_status\|index_status" app/repositories/chunks.py app/services/retrieval.py` 用途各自独立。
- 教师重建（`POST /materials/<id>/reindex`）重写切片与向量，学生无权触发。
  检查：`docker compose exec -T api python -m pytest tests/test_retrieval.py::TestReindex -q` 通过（自定义重建、学生越权、跨班三种）。

## 留存与备份

- 教学数据（材料、切片、会话、调用记录）随班级存在，多数外键为 `ON DELETE CASCADE`；无定时清理任务，过期会话不自动删除，只在每次请求校验 `expires_at`，登出立即删行。
  检查：`grep -n "ON DELETE CASCADE" migrations/*.sql`；`grep -rn "schedule\|cron\|Timer" app/` 无匹配；`tests/test_auth.py::TestLogout::test_logout_invalidates_session_immediately`。
- 备份为每日全量四件（MySQL dump、Qdrant 卷、`uploads/`、`.env` 离线副本），RPO 24 小时。
  检查：`docker compose exec -T db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" campusclaw' > backup.sql` 可执行且文件非空。
- 恢复后必须验证：预置账号可登录、材料可下载、本班检索有命中。
  检查：`docker compose exec -T api python -m pytest -q tests/test_materials.py::TestDownload tests/test_retrieval.py::TestKeywordSearch`。
