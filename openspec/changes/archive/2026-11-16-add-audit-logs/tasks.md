# Tasks

- [x] 1. 迁移与登记
  - [x] 1.1 新增 `migrations/008_audit_logs.sql`
  - [x] 1.2 `app/__init__.py` MIGRATIONS 加一行
  - [x] 1.3 `tests/conftest.py` MIGRATIONS 加一行
  - [x] 1.4 `seeds/seed.py` MIGRATIONS 加一行

- [x] 2. 仓储与服务
  - [x] 2.1 `app/repositories/audit.py`：`insert` / `list_by_class`
  - [x] 2.2 `app/services/audit.py`：`record`（best-effort）/ `insert_commit`（同事务）

- [x] 3. 埋点
  - [x] 3.1 登录 / 登出
  - [x] 3.2 材料上传 / 重建索引 / 下载
  - [x] 3.3 技能增改删（含 skill_name）
  - [x] 3.4 智能体增改
  - [x] 3.5 班级提示词更新
  - [x] 3.6 MCP 登记 / 更新 / 删除 / 连接（成功与失败）/ 断开
  - [x] 3.7 作业创建 / 学生提交
  - [x] 3.8 worker 批改（与结果同事务，含分数与耗时）
  - [x] 3.9 错题讲解（skill_name=错题讲解）

- [x] 4. 查询接口
  - [x] 4.1 `app/routes/api_audit.py`：`GET /api/audit-logs`
  - [x] 4.2 注册蓝图
  - [x] 4.3 `app/routes/api_docs.py` 补 OpenAPI（含错题三条遗漏路径）

- [x] 5. 前端
  - [x] 5.1 教师仪表盘新增「审计日志」卡片
  - [x] 5.2 过滤下拉（action / target_type）+ 刷新

- [x] 6. 测试
  - [x] 6.1 新增 `tests/test_audit.py`（13 个用例）
  - [x] 6.2 全量 `pytest -q` 通过

- [x] 7. 文档
  - [x] 7.1 `reports/security-precheck.md`：SEC-07 转绿 + 证据
  - [x] 7.2 `docs/standards/security.md`：补审计章节
  - [x] 7.3 `README.md`：能力清单与验证路径

- [x] 8. 验收
  - [x] 8.1 `pytest -q` 全绿
  - [x] 8.2 `openspec validate --all --strict --no-interactive` 0 failed
  - [x] 8.3 归档
