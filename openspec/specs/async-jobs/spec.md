# async-jobs Specification

## Purpose
用 MySQL `jobs` 表承载后台任务：入队与业务写入同事务，消费者以 `FOR UPDATE SKIP LOCKED` 领取并按幂等键保证重复投递只产生一份结果；崩溃或超时任务可重新入队。本能力不引入 Redis/Celery 等外部队列，也不做优先级队列与横向扩展。

## Requirements

### Requirement: 任务入队与持久化

系统 SHALL 以 `jobs` 表作为任务队列，任务包含班级、类型、幂等键、载荷、状态、尝试次数、最大尝试次数与最后错误；任务状态只允许 `pending`、`running`、`succeeded`、`failed` 四种。入队 MUST 与产生任务的业务写入在同一事务内提交，不得出现「有业务记录、无任务」的孤儿。

#### Scenario: 提交作业即入队

- **WHEN** 学生成功提交一份作业
- **THEN** `submissions` 行与 `jobs` 行在同一事务内写入，任务状态为 `pending`、`kind=grade`、幂等键为 `grade:<submission_id>`

#### Scenario: 事务失败不留孤儿

- **WHEN** 提交事务在写入任务前失败并回滚
- **THEN** 既没有 `submissions` 行，也没有对应的 `jobs` 行

#### Scenario: 幂等键唯一

- **WHEN** 同一份提交被重复入队（同一 `dedupe_key`）
- **THEN** 第二次入队不新增任务行，返回既有任务标识

### Requirement: 任务领取与执行

消费者 SHALL 以 `SELECT ... FOR UPDATE SKIP LOCKED` 领取任务并立即置为 `running` 且写入 `locked_at`，两个消费者 MUST NOT 同时领取同一条任务；执行成功后置 `succeeded` 并写回业务结果。

#### Scenario: 两个消费者不重复领取

- **WHEN** 两个 worker 同时轮询同一条 `pending` 任务
- **THEN** 只有一个领取成功并置 `running`，另一个跳过该任务

#### Scenario: 成功后状态与结果同时可见

- **WHEN** worker 完成一条批改任务
- **THEN** 任务为 `succeeded`，对应提交在同一事务内获得分数与评语

#### Scenario: 空队列不阻塞

- **WHEN** 队列中没有 `pending` 任务
- **THEN** worker 按固定间隔空转等待，不退出、不报错

### Requirement: 重试、失败与崩溃恢复

任务失败时 SHALL 累加 `attempts` 并写 `last_error`；`attempts >= max_attempts` 时置 `failed` 并把原因写回业务记录。worker 启动时 MUST 把 `locked_at` 超过 60 秒的 `running` 任务重新置为 `pending`，以保证至少一次投递。

#### Scenario: 未达上限则重试

- **WHEN** 批改调用外部网关失败且 `attempts < max_attempts`
- **THEN** 任务回到 `pending` 并记录本次错误，下一轮继续领取

#### Scenario: 达到上限置 failed

- **WHEN** 批改连续失败达到 `max_attempts`
- **THEN** 任务置 `failed`，提交记录保留可读失败原因，不再领取

#### Scenario: 崩溃后重新入队

- **WHEN** worker 崩溃后重启，存在 `running` 且 `locked_at` 超过 60 秒的任务
- **THEN** 这些任务被改回 `pending` 并被重新处理

#### Scenario: 重复执行不产生第二份结果

- **WHEN** 同一条任务被执行两次（至少一次投递导致）
- **THEN** 提交记录只有一份结果，重复执行不新增提交或覆盖为不同分数

#### Scenario: 不存在的任务不被领取

- **WHEN** worker 领取时队列只剩非 `pending` 状态的任务
- **THEN** 不改变任何任务状态，也不写入任何业务结果
