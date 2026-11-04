## ADDED Requirements

### Requirement: 作业创建与班级隔离

系统 SHALL 允许教师在本班创建作业（标题、题目、参考答案），并允许本班成员列出作业；作业读写 MUST 带 `class_id` 条件，跨班访问与不存在资源 MUST 返回同构 404。

#### Scenario: 教师创建作业

- **WHEN** 已登录教师提交合法标题与题目
- **THEN** 返回 201 与作业对象，作业归属该教师所在班级

#### Scenario: 学生无权创建

- **WHEN** 学生调用 `POST /api/assignments`
- **THEN** 返回 403，不产生作业记录

#### Scenario: 跨班不可见

- **WHEN** B 班用户访问 A 班作业详情或其提交
- **THEN** 返回 404，与访问不存在资源同构

#### Scenario: 非法入参被拒

- **WHEN** 创建作业缺少标题或题目
- **THEN** 返回 400 与可读错误，不产生记录

#### Scenario: 未登录被拒

- **WHEN** 未携带 Bearer 令牌调用任一作业或提交端点
- **THEN** 返回 401

### Requirement: 学生提交与异步批改

学生 SHALL 能按班级提交文本答案并获得 `202 Accepted` 与 `taskId`；同一学生对同一作业的重复提交 MUST 复用同一提交与同一任务，不产生第二份结果。批改由 worker 异步完成，批改结果为 0–100 分数与评语。

#### Scenario: 提交返回 202 与任务标识

- **WHEN** 学生向本班作业提交文本答案
- **THEN** 返回 202，body 含 `taskId` 且对应一条 `pending` 批改任务

#### Scenario: 重复提交幂等

- **WHEN** 同一学生对同一作业再次提交
- **THEN** 不新增提交或任务，返回同一 `taskId`，最终只有一份批改结果

#### Scenario: 轮询可见状态流转

- **WHEN** 学生轮询自己提交的状态
- **THEN** 状态从 `pending` 变为 `running`，完成后变为 `succeeded` 并给出分数与评语

#### Scenario: 学生只能看自己的提交

- **WHEN** 学生访问他人的提交
- **THEN** 返回 404，不泄露存在性与内容

#### Scenario: 教师可看本班提交

- **WHEN** 本班教师查询任一提交
- **THEN** 返回 200 与该提交的答案、状态、分数与评语

#### Scenario: 批改失败可读

- **WHEN** 批改在重试上限内始终失败
- **THEN** 提交状态为 `failed` 且带可读失败原因，分数为空

#### Scenario: 模型输出非结构化仍可用

- **WHEN** 模型返回文本而非 `{"score","feedback"}` JSON
- **THEN** 状态仍为 `succeeded`，分数为空，评语保存模型原文

#### Scenario: 不存在的作业或提交

- **WHEN** 访问不存在的作业或提交 id
- **THEN** 返回 404
