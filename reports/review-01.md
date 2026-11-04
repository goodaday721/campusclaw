# 交叉评审记录 01（第 8 课异步批改）

- 变更：`2026-11-04-async-grading-tasks`
- 评审人：第二视角交叉评审（对实现与规约独立复核）
- 日期：2026-11-04
- 结论：**通过，带 2 条已登记红项进入下一课**

## 评审清单

| 检查点 | 结果 | 说明 |
| --- | --- | --- |
| 迁移可重复执行 | 通过 | `CREATE TABLE IF NOT EXISTS`；三处 MIGRATIONS 已登记 |
| 路由不写 SQL | 通过 | `app/routes/api_grading.py` 只调仓储 |
| 按 id 读取带作用域 | 通过 | `find_assignment` / `find_submission` 均带 `class_id` |
| 跨班 404 同构 | 通过 | apitest 与 pytest 均有跨班用例 |
| 提交 + 任务同事务 | 通过 | 停 worker 实测：提交成功且任务成对存在 |
| 重复提交幂等 | 通过 | 8 并发全部 202，提交 1 条、任务 1 条 |
| 结果只写一次 | 通过 | `graded_at IS NULL` 条件 + 重放用例 |
| 重试与失败可见 | 通过 | `max_attempts=3`，失败后提交 `failed`、分数空 |
| 崩溃恢复 | 通过 | 启动 `requeue_stale(60s)`，单测覆盖 |
| 接口文档同步 | 通过 | `/openapi.json` 含 4 个新路径，版本 7.0.0 |
| 前端转义 | 通过 | 标题/题目/评语均经 `escapeHtml` |
| 测试门禁 | 通过 | pytest 155、e2e 82、apitest 33 |
| 安全自查 | 部分通过 | SEC-06、SEC-07 为红，已登记补救项 |

## 评审发现

1. **并发 500（已修复）**：首版 `enqueue` 的「先查后插」在并发下触发唯一键冲突。改为 `ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)`，复测 8 并发全 202。
2. **SEC-06 红**：缺少依赖漏洞扫描工具，无法给出 CVE 基线。接受为红项，进入下一课。
3. **SEC-07 红**：审计日志字段不足（缺操作类型/对象/技能标识/用量耗时）。接受为红项，进入下一课。
4. **文档一致性**：第 7 课 AGENTS.md 的两条非目标（不做作业批改、不做异步队列）已在本变更中显式推翻并同步修改，避免「规范与代码打架」。

## 复核命令

```bash
docker compose exec -T api python -m pytest -q            # 155 passed
docker compose exec -T api python e2e_test.py              # 82 passed
docker compose exec -T api python apitest/run_all.py       # 33 passed
docker compose exec -T api python scripts/check_security.py
openspec validate --all --strict --no-interactive
```
