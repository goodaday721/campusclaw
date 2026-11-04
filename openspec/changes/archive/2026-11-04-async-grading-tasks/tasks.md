# Tasks: add-async-grading-tasks

## 1. 数据层与队列语义

- [x] 1.1 新增 `migrations/006_grading.sql`：`assignments`（id、class_id、title、question、reference_answer、created_by、created_at，FK 到 classes 级联删除）、`submissions`（id、assignment_id、class_id、student_id、answer、score 可空、feedback、graded_at、created_at、`UNIQUE(assignment_id, student_id)`）、`jobs`（id、class_id、kind、dedupe_key 唯一、payload JSON、status、attempts、max_attempts、last_error、locked_at、created_at、updated_at）；`app/__init__.py`、`tests/conftest.py`、`seeds/seed.py` 三处 MIGRATIONS 追加
  - verify: 容器内迁移后可 `SHOW TABLES` 见三张新表；重复执行迁移不报错
- [x] 1.2 新增 `app/repositories/grading.py`：assignments（list_by_class/find_scoped/create）、submissions（find_owned/find_by_class/upsert_for_student/update_result/find_by_id_scoped）、jobs（enqueue/find_by_dedupe/claim_next/mark_succeeded/mark_failed/requeue_stale）；全部 SQL 参数化且读取带 `class_id` 或归属条件
  - verify: `grep -rn "SELECT\|INSERT\|UPDATE" app/routes/api_grading.py` 无匹配；重复提交只复用一条 submissions 与一条 jobs

## 2. 批改服务与 worker

- [x] 2.1 新增 `app/services/grading.py`：构造批改消息（参考答案 + 学生答案 + 要求返回 `{"score", "feedback"}`）、解析结果、网关异常分类；解析失败时 `score` 置空、`feedback` 放模型原文
  - verify: pytest fake 网关：合法 JSON 解析出分数；非 JSON 文本走降级；`GatewayUnavailable` 抛可重试异常
- [x] 2.2 新增 `app/worker.py`：读配置直连数据库、启动时 `requeue_stale_running(60s)`、循环 `FOR UPDATE SKIP LOCKED` 领取并置 running、调用批改服务、同事务写回提交结果与任务状态、超过 `max_attempts` 置 failed
  - verify: 容器内 `python -m app.worker` 可启动并处理一条 pending 任务；无任务时按间隔空转；日志为单行 JSON

## 3. 路由与接口

- [x] 3.1 新增 `app/routes/api_grading.py`：`POST /api/assignments`（教师，400 校验）、`GET /api/assignments`（本班）、`POST /api/assignments/<int:assignment_id>/submissions`（学生本人，202 + taskId）、`GET /api/submissions/<int:submission_id>`（本人或本班教师）；跨班与越权一致 404；重复提交复用同一提交与任务
  - verify: pytest：教师建作业 201、学生提交 202 且 taskId 对应 jobs、重复提交 taskId 相同、B 班访问 A 班 404、未登录 401、学生建作业 403
- [x] 3.2 `app/__init__.py` 注册 grading 蓝图；`docker-compose.yml` 增 `worker` 服务（复用 api 镜像，`python -m app.worker`，env_file `.env`，depends_on db，不映射宿主机端口）
  - verify: `docker compose config --services` 恰为 web、api、db、qdrant、mcp-demo、worker；`ports` 只出现在 web 段

## 4. 接口文档与前端

- [x] 4.1 `app/routes/api_docs.py` 版本 `7.0.0`，补 `grading` tag 与四个端点（入参、出参、401/403/404/400/202 错误码与 bearerAuth）
  - verify: `/openapi.json` 含四条新 path；Swagger 页可见并可试调
- [x] 4.2 `app/routes/pages.py` 教师侧新增「作业与异步批改」卡（建作业、看本班作业列表）；学生侧同卡内提供「提交作业」（提交文本、轮询 pending→running→succeeded 展示分数与评语）；服务端数据经 `escapeHtml`
  - verify: 浏览器：教师建作业 → 学生提交看到任务状态流转 → 完成后显示分数与评语

## 5. 测试与门禁

- [x] 5.1 新增 `tests/test_grading.py`：正常（建作业/提交/worker 成功）、失败（网关不可用重试后 failed、非法入参 400、未登录 401、学生建作业 403）、边界（跨班与越权 404、重复提交幂等、`max_attempts` 用尽、超过 60s 的 running 被重新入队）
  - verify: 容器内 `docker compose exec -T api python -m pytest -q` 全绿且无 skip
- [x] 5.2 `apitest/cases/` 与 `e2e_test.py` 追加：登录取令牌 → 建作业 → 提交 202 → 轮询至 succeeded；重复提交只出一份结果
  - verify: `python e2e_test.py`、`python apitest/run_all.py` 退出码 0

## 6. 第 8 课安全自查与报告

- [x] 6.1 新增 `scripts/check_security.py` 与 Makefile `check-security` 目标（SEC-05 密钥扫描、SEC-06 依赖漏洞基线）
  - verify: `make check-security` 可运行并输出每项 SEC 编号与结论
- [x] 6.2 实测 SEC-01~SEC-07 并归档 `reports/`：`security-precheck.md`、`risk-authz.md`、`risk-concurrency.md`、`risk-transaction.md`、`security-baseline.md`、`review-01.md`；至少保留 1 条红（计划 SEC-06 审计工具缺失、SEC-07 日志缺操作类型/对象/技能标识/用量耗时）
  - verify: 每条结论附可复现命令与实测输出；`review-01.md` 为交叉评审记录
- [x] 6.3 并发判据（重复提交只出一份结果）与事务判据（停 worker 提交 → 启 worker 恰好一次、无孤儿）实测留证
  - verify: 证据写入 `reports/risk-concurrency.md` 与 `reports/risk-transaction.md`

## 7. 文档同步与归档

- [x] 7.1 同步 `AGENTS.md`（五服务→六服务、删除两条非目标、新增异步队列节）、`docs/standards/{backend,data,ops,testing}.md`、`README.md`（异步能力、六服务、`make check-security`、reports 路径、验证链路）
  - verify: `openspec validate --all --strict --no-interactive` 输出 0 failed；README 含「验证」章节与新链路
- [x] 7.2 归档变更到 `openspec/changes/archive/2026-11-04-async-grading-tasks/`，delta 合并回 `openspec/specs/`
  - verify: `openspec list` 输出 `No active changes found.`；`openspec list --specs` 列出 13 个能力 spec
