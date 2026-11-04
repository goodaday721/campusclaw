# 风险清单：并发与幂等（risk-concurrency）

范围：同一学生并发重复提交、多消费者同时领取任务、崩溃后重投。

## 设计约束

1. `submissions` 上 `UNIQUE(assignment_id, student_id)`：一个学生对一份作业只有一条提交。
2. `jobs.dedupe_key` 唯一，值为 `grade:<submission_id>`：一条提交只有一个任务。
3. worker 用 `SELECT ... FOR UPDATE SKIP LOCKED` 领取，随后置 `running` 并记录 `locked_at`。
4. 启动时把 `locked_at` 超过 60 秒的 `running` 任务改回 `pending`（至少一次投递 + 幂等落库）。

## 发现与修复

**发现（红 → 绿）**：首版 `enqueue` 先 `SELECT dedupe_key` 再 `INSERT`。8 个并发提交时，多个请求同时查不到既有任务，随后 `INSERT` 触发唯一键冲突，接口返回 500。

**修复**：改为单条

```sql
INSERT INTO jobs (...) VALUES (...)
ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)
```

竞争失败方直接拿到胜方的任务 id，不再抛 1062。

## 实测证据（修复后）

8 个并发请求，同一学生对同一作业提交：

```text
parallel submit statuses = [202]
distinct submissionIds = [24]
distinct taskIds = [24]
submissions rows = 1
recent jobs = [{'id': 24, 'status': 'pending', 'attempts': 0, 'dedupe_key': 'grade:24'}, ...]
```

结论：所有请求 202；提交 1 条、任务 1 条；worker 只批改一次，最终提交只有一份结果。

## 用例

- `tests/test_grading.py::TestSubmissionsAPI::test_resubmit_is_idempotent`
- `tests/test_grading.py::TestWorker::test_replayed_job_keeps_first_result`
- `apitest/cases/api/grading/assignments/item/submissions/POST.py`（重复提交复用同一 taskId）

## 残余风险

1. 单实例部署下 `SKIP LOCKED` 已足够；若未来横向扩展，需要额外监控任务饥饿与锁等待。
2. 批改调用超过 60 秒会被重新入队，可能与仍在执行的慢调用重叠；依靠「结果只写一次」保证不出现第二份结果。
