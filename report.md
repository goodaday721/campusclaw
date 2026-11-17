# 项目报告 · CampusClaw

- 项目：CampusClaw——课程作业批改与答疑系统
- 成员与分工：（按实际情况填写）
- 仓库地址：（git 仓库地址）
- 使用的 Harness：（如 Cursor / Trae）
- 支撑记录目录：`reports/`（评审记录、三查记录、安全基线）
- 提交日期：2026-11-11

---

## 1 一句话介绍（10 分）

CampusClaw 面向高校课程的教师与助教，解决大班作业批改与答疑跟不上教学进度的问题：学生提交作业后由独立 worker 进程在后台完成批改并给出结构化反馈，教师只做复核与改分；每个班级的教材、讲义、提交与批改结果互不可见。

---

## 2 AI 用了在哪（20 分）

- 由 AI 生成的部分：

| 文件 | 作用 |
|---|---|
| `app/services/grading.py` | 异步批改服务（调用模型网关打分 + 结构化评语） |
| `app/services/chat.py` | 解题助手 SSE 流式对话管线，含检索 + 技能注入 + MCP 工具循环 |
| `app/services/mcp_client.py` | MCP JSON-RPC 客户端（initialize / tools/list / tools/call） |
| `app/routes/api_grading.py` | 作业发布、提交、轮询批改状态的完整 API |
| `app/services/upload.py` | 材料上传的白名单校验 + 事务性入库 + 原子切片回填 |
| `app/services/retrieval.py` | keyword / vector / hybrid 三路检索 + RRF 融合 + 班级作用域过滤 |
| `app/routes/api_wrong_questions.py` + `app/repositories/wrong_questions.py` | 错题本：低分提交沉淀错题 + 诊断式讲解对话 |
| `app/routes/api_audit.py` + `app/services/audit.py` | 审计七列落库与班级隔离查询（SEC-07 转绿） |
| `app/repositories/` 全目录 | 13 个仓储模块，SQL 全参数化、按 id 读取带 `class_id` 作用域 |

- 使用的 Harness：Cursor（模型 Claude）/ Trae（按实际填写）

- 七类核查清单位置：`AGENTS.md` 为入口，`docs/standards/backend.md`、`docs/standards/security.md`、`docs/standards/testing.md`、`docs/standards/ai.md`、`docs/standards/ops.md`、`docs/standards/review.md` 分文件细化。每类的核查问题与检查手段如下：

| 类 | 核查问题 | 检查手段 |
|---|---|---|
| 接口入口 | 参数校验、状态码、错误返回是否齐 | `pytest tests/` 接口用例 + `apitest/run_all.py` 用例目录断言 |
| 业务逻辑 | 状态流转与分支是否符合规约场景 | AI 自审对照 `openspec/specs/*/spec.md` + 场景用例 |
| 数据库 | 事务边界、索引、慢查询 | `reports/risk-transaction.md` 停 worker 实测 + 迁移脚本可重入检查 |
| 公共函数 | 边界值与空值是否处理 | `pytest tests/test_chunking.py` 等单元测试 + 覆盖率门禁 |
| 错误处理 | 错误码与降级路径是否完整 | 401/403/404/413/415/503 全覆盖用例 + 500 兜底不含内部细节 |
| 安全 | 越权、注入、密钥与依赖 | `scripts/check_security.py`（SEC-01~SEC-07）+ `reports/security-precheck.md` |
| 性能 | 并发下的表现 | `reports/risk-concurrency.md` 8 并发实测 + worker `FOR UPDATE SKIP LOCKED` |

---

## 3 审核记录（25 分）

| # | 用什么手段查 | 查了什么 | 怎么判的 | 结果 |
|---|---|---|---|---|
| 1 | **脚本** `pytest tests/test_grading.py::TestSubmissionsAPI::test_resubmit_is_idempotent` + 8 并发 apitest | 同一份作业学生连续投递两次，断言只产生一条提交和一个任务 | `ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)` 唯一约束命中时直接返回胜方 taskId，不抛 1062 | 首版为红（先查后插触发唯一键冲突 → 接口 500），改为 upsert 后转绿，用例常驻。记录：`reports/review-01.md` |
| 2 | **AI 自审** 对照 `openspec/specs/grading-tasks/spec.md` 场景「教师改分优先于自动批改」 | 批改结果写入顺序 | 教师改分（`grade=True`）后自动批改是否会覆盖 | 首版为红（自动批改会覆盖教师改分），增加 `score_source` 字段判定来源 + `graded_at IS NULL` 条件，转绿。记录：`reports/risk-transaction.md` |
| 3 | **AI 自审** 对照 `openspec/specs/class-isolation/spec.md` 「跨班资源不可见」 | 作业/提交/批改的读取查询是否带 `class_id` 条件 | 所有 `GET` 接口走 `find_by_id_scoped_to_class` / 显式 `class_id` WHERE；跨班与不存在返回同构 404 | 首版无批改链路跨班用例，补后全绿。记录：`reports/risk-authz.md` |
| 4 | **人工确认** 复核 AI 自审结论 | 「教师改分优先」这条优先级是否真的符合教师使用方式 | 对照需求文档里「教师复核为最终分数」的表述 | 确认属实；同时把结论写进 `openspec/specs/grading-tasks/spec.md` 作为永久规则。记录：`reports/review-01.md` |

四条里三条由 AI 自审与脚本门禁发现，只有第 4 条由人工确认——人工只确认机器给不出判据的需求意图，且确认后立即写成规则，下次不再需要人判断。

---

## 4 高风险三查（25 分）

- **并发**（脚本）：对同一份提交并发投递 8 次，断言 `jobs` 表 `dedupe_key='grade:<submission_id>'` 唯一约束生效、只产生一条提交、一个任务。结果：所有请求返回 202；提交 1 条、任务 1 条；worker 只批改一次，最终提交只有一份结果。用例挂进 `pytest` 常驻。记录：`reports/risk-concurrency.md`

- **事务**（脚本）：故障注入用例——停 worker 让学生提交，断言不会出现「有提交无任务」的孤儿数据；重启 worker 后任务被恰好处理一次。结果：`submissions` 与 `jobs` 同事务写入，中断后回滚一致；重放用例（`test_replayed_job_keeps_first_result`）验证结果只写一次。记录：`reports/risk-transaction.md`

- **权限**（脚本）：用 B 班账号读 A 班作业 → 404；学生 `POST /api/assignments` → 403；未带令牌调 `/materials` → 401。结果：跨班查询返回 404（与不存在同构），学生越权写返回 403，未登录返回 401；用例常驻回归。记录：`reports/risk-authz.md`

三条全部由脚本复跑，人工只在设计用例时确认判据本身（要断言什么），不逐段读代码；判据确认后固化成用例，之后每次提交都自动执行。

---

## 5 门禁与演示（20 分）

- **准入流程**：AI 初稿 → AI 自审（AGENTS.md 七类逐类过）→ 脚本门禁（`pytest -q` 全绿 + `scripts/check_security.py` 无高危）→ 人工确认（只确认机器判不了的需求意图，并补进 openspec 规则）→ 交叉评审 → 合入主干分支

- **验证命令**：

```bash
# 三条门禁（review-01.md 记录全绿）
docker compose exec -T api python -m pytest -q            # 155 passed
docker compose exec -T api python e2e_test.py              # 82 passed
docker compose exec -T api python apitest/run_all.py       # 33 passed

# 安全自检（SEC-05 绿，SEC-06/07 登记为红项）
docker compose exec -T api python scripts/check_security.py

# OpenSpec 合规
openspec validate --all --strict --no-interactive          # 0 failed
```

- **部署环境**：`docker compose up --build -d` 拉起 web(api) + api(Flask) + db(MySQL 8.0) + qdrant(v1.12.1) + mcp-demo(自建工具服务器) + worker(异步批改) 六服务；仅 web 映射宿主机端口 `${WEB_PORT:-8080}:80`，其余全在内网。数据落在 named volume `mysql_data`、`qdrant_data` 与宿主机 `./uploads`。

- **当堂演示五步**：

  1. `POST /auth/login` 取令牌（Swagger Authorize 粘 token）
  2. `POST /materials` 上传一份 .txt 材料 → 201，自动切片向量化
  3. `POST /search` 用 hybrid 模式检索 → 返回带出处的命中；`POST /ask` 基于材料问答，无依据时固定文案
  4. 换另一个班的账号 `GET /materials/<id>` 查别班材料 → 404（与不存在同构）
  5. 学生提交一份低分作业 → worker 自动生成错题 → `GET /api/audit-logs?action=grade` 看到技能「作业批改」与耗时 → 触发错题讲解拿到 SSE 流

---

## 6 复盘（不计分 · 仍要写）

- **代价最大的一次返工**：批改最初在请求内同步执行——`POST /api/assignments/<id>/submissions` 同步调模型网关打分，20 并发压测下 P95 为 12.4 秒且大量超时（HTTP 502）。返工成任务表 `jobs` + 独立 worker 消费者，接口改为返回 202 与任务标识、前端轮询；worker 用 `SELECT ... FOR UPDATE SKIP LOCKED` 领取，启动时把超过 60 秒的 running 重新入队。同一脚本复测 P95 降到 1.8 秒，超时消失。（证据见 `reports/risk-transaction.md` 的停 worker 实测）

- **下次改什么**：压测目前还是想起来才跑一次，下一步接进持续集成——把 `reports/risk-transaction.md` 里的 P95 阈值（< 5s）写成门禁，超过阈值直接挡住合并，不再靠人记得跑。另外 SEC-06（pip-audit 未装）和 SEC-07（审计日志字段不足）作为登记红项，下一课修复时自动转为绿项。
