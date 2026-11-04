# 风险清单：事务与一致性（risk-transaction）

范围：提交事务（submissions + jobs）、批改事务（提交结果 + 任务状态）、孤儿任务。

## 事务边界

1. **提交**：`upsert_submission` 与 `enqueue` 在同一个数据库事务内提交；失败则整体回滚，不出现「有提交、无任务」。
2. **批改**：`finish_submission` 与 `finish_job` 在同一事务内提交；重复执行时 `finish_submission` 只在 `graded_at IS NULL` 时写入，首份结果不被覆盖。
3. **重投**：worker 启动时 `requeue_stale` 单独事务提交，不影响业务行。

## 停 worker 实测（事务判据）

步骤与结果：

```text
1) docker compose stop worker
2) 学生提交作业 → 202
   submitted submission=17 task=17 status=pending
   submissions rows = 1
   job before worker = {'status': 'pending', 'attempts': 0, 'locked_at': None}
3) docker compose start worker
4) 轮询至终态
   final submission = {'id': 17, 'status': 'succeeded', 'score': 100, ...}
   exact submission rows = 1
   job after worker = {'status': 'succeeded', 'attempts': 0, 'last_error': None}
```

结论：

- 停 worker 时提交仍成功，且提交与任务成对存在（无孤儿提交、无孤儿任务）。
- 启 worker 后任务被处理恰好一次，提交只有一份结果。
- 失败路径由 `tests/test_grading.py::TestWorker::test_gateway_failure_retries_then_fails` 覆盖：重试 3 次后任务 `failed`、提交 `failed`、`score` 为空。

## 残余风险

1. 若模型调用成功但写库失败，任务会重新入队并再次调用模型（至少一次语义）；结果只写一次，但会产生重复计费。当前不做幂等外部调用缓存。
2. 迁移脚本按 `;` 切分，SQL 注释中不能出现分号（本课已在注释中规避）。
3. `ON DELETE CASCADE` 下删除班级会连带删除作业、提交与任务；当前无删除接口，风险不可达。
