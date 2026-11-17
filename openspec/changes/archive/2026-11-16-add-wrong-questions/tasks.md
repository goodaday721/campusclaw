# Tasks

- [ ] 1. 迁移与登记
  - [ ] 1.1 新增 `migrations/007_wrong_questions.sql`（建表 + 唯一约束 + 外键）
  - [ ] 1.2 `app/__init__.py` MIGRATIONS 加一行
  - [ ] 1.3 `tests/conftest.py` MIGRATIONS 加一行
  - [ ] 1.4 `seeds/seed.py` MIGRATIONS 加一行

- [ ] 2. 仓储层
  - [ ] 2.1 新增 `app/repositories/wrong_questions.py`：
    - `upsert_from_submission(conn, submission_id, class_id)`
    - `list_for_student(conn, student_id, class_id)`
    - `list_for_class(conn, class_id)`
    - `find_by_id_scoped(conn, wq_id, class_id, student_id=None)`

- [ ] 3. Worker 写入
  - [ ] 3.1 `app/worker.py::_succeed` 在同事务内追加 `if score < 60: upsert`
  - [ ] 3.2 单测：mock grading 返回低分 → 错题表新增 1 行；返回高分 → 表不变；重放 job → 行数仍 1

- [ ] 4. 路由层
  - [ ] 4.1 新增 `app/routes/api_wrong_questions.py`：
    - `GET /api/wrong-questions`（按角色分发）
    - `GET /api/wrong-questions/<int:wq_id>`（同构 404）
    - `POST /api/wrong-questions/<int:wq_id>/explain`（创建会话 + SSE）
  - [ ] 4.2 在 `app/__init__.py` 注册蓝图
  - [ ] 4.3 在 `app/routes/api_docs.py` 补 OpenAPI schema

- [ ] 5. 技能注册
  - [ ] 5.1 `seeds/seed.py` 新增 `SEED_WRONG_QUESTION_SKILL` 常量
  - [ ] 5.2 `_seed_assistant()` 里追加：两班各插入该技能 + 绑到默认解题助手
  - [ ] 5.3 验证：seed 后 `SELECT name FROM skills WHERE name='错题讲解'` 返回 2 行

- [ ] 6. 前端
  - [ ] 6.1 学生 dashboard 加「我的错题」卡片：列表 + 每条一个「讲解」按钮
  - [ ] 6.2 教师 dashboard 加「本班错题」卡片：列表 + 讲解按钮
  - [ ] 6.3 讲解按钮复用现有 SSE 对话组件

- [ ] 7. 测试
  - [ ] 7.1 新增 `tests/test_wrong_questions.py`，覆盖 7 个用例
  - [ ] 7.2 全量 `pytest -q` 通过

- [ ] 8. 文档
  - [ ] 8.1 `README.md` 能力清单 + 验证路径补错题讲解
  - [ ] 8.2 `AGENTS.md` 第 7 节加技能清单（解题引导 / 作业批改 / 错题讲解）
  - [ ] 8.3 `docs/standards/ai.md` 技能章节补错题讲解
  - [ ] 8.4 `docs/standards/testing.md` 补 `tests/test_wrong_questions.py`

- [ ] 9. 验收
  - [ ] 9.1 `pytest -q` 全绿
  - [ ] 9.2 `openspec validate --all --strict --no-interactive` 0 failed
  - [ ] 9.3 归档：`openspec archive 2026-11-16-add-wrong-questions --yes`
