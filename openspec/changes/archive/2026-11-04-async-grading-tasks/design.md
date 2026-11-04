# 设计：add-async-grading-tasks

## 技术栈映射

| 组件 | 技术 | 说明 |
| --- | --- | --- |
| 队列 | MySQL 表 `jobs` | 不引入中间件；`FOR UPDATE SKIP LOCKED` 领取，天然支持多消费者 |
| 消费者 | 独立容器 `worker` | 复用 api 镜像，`python -m app.worker` 轮询；与 api 同网络、同 `.env` |
| 批改 | `app/services/grading.py` + `model_gateway.chat` | 服务端调用课程网关，密钥不出服务端 |
| 提交接口 | `app/routes/api_grading.py` | 只做 HTTP 边界，SQL 全参数化 |
| 数据访问 | `app/repositories/grading.py` | 所有读取带 `class_id` 或归属条件 |

## 关键决策

1. **队列就是数据库表**。课程目标是理解异步与投递语义，不是引入中间件；一张表 + 独立容器即可演示「停消费者 → 提交 → 启消费者 → 恰好一次」。
2. **提交即入队，同事务**。`submissions` 行与 `jobs` 行在同一事务写入，避免「有提交无任务」的孤儿；提交接口在事务提交后才返回 202。
3. **幂等键唯一**。`jobs.dedupe_key = grade:<submission_id>`，且 `submissions` 上有 `UNIQUE(assignment_id, student_id)`：重复提交复用同一条提交与同一个任务，只出一份结果。
4. **领取用 SKIP LOCKED**。`SELECT ... FOR UPDATE SKIP LOCKED` 后立即置 `running`，避免两个消费者拿到同一条任务。
5. **至少一次投递 + 幂等落库**。worker 启动时把 `running` 且 `locked_at` 超过 60 秒的任务改回 `pending`（崩溃恢复）；写结果时只更新仍处于 `running` 的任务，重复执行不会产生第二条提交结果。
6. **重试有上限**。`attempts >= max_attempts` 置 `failed` 并把 `last_error` 写回提交记录；网关未配置视为可重试的外部依赖不可达。
7. **批改输出结构化但不强求**。要求模型返回 `{"score": 0-100, "feedback": "..."}`；解析失败不丢内容，`score` 置空、评语放模型原文，状态仍为 succeeded。
8. **跨班与越权一律 404**。学生只能轮询自己的提交，教师可看本班提交；不存在与无权同构。
9. **worker 不依赖 Flask**。消费者直接读配置、连库、调网关，不注册路由，避免把 HTTP 层带进后台进程。
10. **服务数变更需同步规范**。compose 由五服务变六服务，只有 web 映射宿主机端口；`AGENTS.md` 与运维规范同批更新。

## 风险与取舍

- 单实例 worker 足够演示；扩展多实例时 `SKIP LOCKED` 已能防重复领取，但 `locked_at` 超时阈值需大于最长批改耗时。
- 作业与批改会调用真实网关，e2e/apitest 里对状态只断言到 `pending` 或短轮询 `succeeded`，避免评测受网关抖动影响。
