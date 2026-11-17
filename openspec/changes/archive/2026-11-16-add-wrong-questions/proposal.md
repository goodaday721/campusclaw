# 变更：add-wrong-questions

## Why

课件《学期项目说明》把「错题」和「错题讲解技能」明确列在**必做**项里：

> 学生端：登录、本班首页、讲义与检索、助手对话、交作业、批改与**错题**
> 三项技能：解题引导、作业批改、**错题讲解**，可启用、停用并验收

当前代码库只实现了「解题引导」和「作业批改」两个技能，`wrong_questions` 表与对应路由完全缺失。本次补齐该必做能力，让判错提交自动沉淀为错题，并由新技能驱动针对性讲解。

## What Changes

- 新增迁移 `migrations/007_wrong_questions.sql`：`wrong_questions` 表（id, class_id, submission_id, student_id, question, student_answer, reference_answer, reason, created_at），`UNIQUE(submission_id)` 保证同一提交只产生一条错题。
- 三处 MIGRATIONS 登记同步：`app/__init__.py`、`tests/conftest.py`、`seeds/seed.py`。
- 新增仓储 `app/repositories/wrong_questions.py`：所有读取带 `class_id` 作用域；学生再叠加 `student_id` 过滤。
- 改 `app/worker.py`：批改成功且 `score < 60` 时，与 `finish_submission` 同一事务写入错题（`INSERT ... ON DUPLICATE KEY UPDATE` 幂等）；`reason` 取 feedback 的前 200 字符。
- 新增路由：
  - `GET /api/wrong-questions`：学生返回自己的，教师返回本班全部。
  - `GET /api/wrong-questions/<int:id>`：跨班/不存在返回同构 404；学生跨他人也返回 404。
  - `POST /api/wrong-questions/<int:id>/explain`：在指定错题上触发讲解对话，内部创建一条 conversation 并流式返回（复用 `app/services/chat.py` 的 SSE 管线）。
- 新增第三个内置技能「错题讲解」：在 `seeds/seed.py` 注册到 A/B 两班，绑定到默认解题助手；技能 system_prompt 要求先诊断错因（概念不清/计算失误/审题偏差），再分步引导，**不直接给答案**。
- 开放接口全部进入 `app/routes/api_docs.py` 的 `/openapi.json`。
- 补 pytest 用例：错题生成（低分写入 / 高分不写）、跨班隔离、教师可见本班 / 学生只见自己、讲解对话触发与流式响应。
- 同步更新 `AGENTS.md`、`docs/standards/{backend,ai,testing}.md` 与 `README.md` 的能力清单与验证路径。

## Non-Goals

- 不做错题本按知识点聚类、不做掌握度统计。
- 不做错题的「已掌握」标记、不做掌握曲线。
- 不做错题导出 PDF、不对外分享。
- 不修改现有 grading 的打分逻辑与 prompt；只在 worker 末尾追加写错题动作。
- 不做错题的批量清理、不做教师对学生错题的批注。

## Capabilities

- `wrong-questions`（新增）：错题生成、按学生/班级隔离的查询、错题讲解对话触发。
- `assistant-skills`（修改）：新增第三个内置技能「错题讲解」，与现有解题引导、作业批改并列。
- `api-docs`（修改）：三个新端点进入 OpenAPI 文档。
