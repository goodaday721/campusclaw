# 变更：add-audit-logs

## Why

第 9 课要求「形成可查询的审计记录」，第 8 课安全清单里 SEC-07「审计日志七列」被登记为红项：现有的请求日志只有 ts/method/path/status/ms/class_id/user_id，缺少**操作类型、对象、技能标识、用量与耗时**四类字段，且只存在于容器 stdout，无法按班级查询。

本次把审计从「打印日志」升级为「入库可查」：新增 `audit_logs` 表与教师查询接口，覆盖登录、材料、技能、智能体、提示词、MCP、作业、提交、批改、错题讲解十类操作。

## What Changes

- 新增迁移 `migrations/008_audit_logs.sql`：`audit_logs` 表含七个业务列——`action`（操作类型）、`target_type`（对象）、`target_id`、`actor_id`、`class_id`、`skill_name`（技能标识）、`detail`（用量与耗时等 JSON），另有 `created_at`。
- 三处 MIGRATIONS 登记同步：`app/__init__.py`、`tests/conftest.py`、`seeds/seed.py`。
- 新增仓储 `app/repositories/audit.py`：`insert` 写入、`list_by_class` 按班级 + 可选 action/target_type 过滤，全部参数化。
- 新增服务 `app/services/audit.py`：`record` 独立事务 best-effort 写入（审计故障不影响业务），`insert_commit` 供 worker 与批改结果同事务写入。
- 埋点覆盖：
  - `auth.py`：login / logout
  - `materials.py`：上传（create）、重建索引（reindex）、下载（download）
  - `api_skills.py`：创建 / 更新 / 删除（skill_name 记录技能名）
  - `api_agents.py`：创建 / 更新
  - `api_prompt.py`：更新
  - `api_mcp.py`：服务器登记 / 更新 / 删除 / 连接（成功与失败）/ 断开
  - `api_grading.py`：作业创建、学生提交
  - `worker.py`：批改成功（`skill_name="作业批改"`，`detail` 含分数、耗时 ms、错题 id），与结果同事务
  - `api_wrong_questions.py`：错题讲解（`skill_name="错题讲解"`）
- 新增 `GET /api/audit-logs`：教师专用、班级隔离，支持 `limit` / `action` / `target_type` 过滤；未知过滤值 400；学生 403；未登录 401。
- 新增并在 `/openapi.json` 描述：`GET /api/audit-logs`（同时补登上一变更遗漏的 `/api/wrong-questions` 三条路径）。
- 教师仪表盘新增「🧾 审计日志」卡片，按 action/target_type 过滤展示。
- 更新 `reports/security-precheck.md`：SEC-07 由红转绿，附查询证据。

## Non-Goals

- 不做审计行的过期清理与归档策略（数据量与课程周期都小）。
- 不做审计的实时告警、导出 CSV/PDF。
- 不改 stdout 请求日志格式（保留一行 JSON；七列以数据库行承载）。
- 不做操作回放与撤销。

## Capabilities

- `audit-log`（新增）：审计行的七列模型、写入时机、班级隔离查询与过滤。
- `api-docs`（修改）：新增 `GET /api/audit-logs` 与错题三条路径的 OpenAPI 描述。
