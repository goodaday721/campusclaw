## ADDED Requirements

### Requirement: 错题自动生成

系统 SHALL 在 worker 批改完成且 `score < 60` 时，与 `finish_submission` 同一事务写入 `wrong_questions` 表；同一提交 MUST 至多产生一条错题（由 `UNIQUE(submission_id)` 约束保证）；题目/学生答案/参考答案 MUST 做冗余存储。

#### Scenario: 低分提交产生错题

- **WHEN** worker 完成一次批改且分数为 40，feedback 为「未识别方程类型」
- **THEN** `wrong_questions` 表新增 1 行，字段对应该提交，`reason` 为 feedback 前 200 字

#### Scenario: 高分提交不产生错题

- **WHEN** worker 完成一次批改且分数为 85
- **THEN** `wrong_questions` 表行数不变

#### Scenario: 重放 job 幂等

- **WHEN** 已写入错题的提交再次被执行（job 被重置为 pending 后重跑）
- **THEN** `UNIQUE(submission_id)` 触发 ON DUPLICATE KEY UPDATE，行数仍为 1

### Requirement: 错题查询的班级与归属隔离

系统 SHALL 提供 `GET /api/wrong-questions` 列表端点（学生返回自己的，教师返回本班全部）与 `GET /api/wrong-questions/<int:id>` 详情端点；跨班访问、学生跨他人访问、查询不存在 id 时 MUST 返回同构 404。

#### Scenario: 学生查自己的列表

- **WHEN** student_a 调用 `GET /api/wrong-questions`
- **THEN** 返回 `{"wrong_questions": [...]}`，仅含 student_a 自己的记录

#### Scenario: 教师查本班列表

- **WHEN** teacher_a 调用 `GET /api/wrong-questions`
- **THEN** 返回本班全部错题，每条 `classId=1`

#### Scenario: 跨班列表为空

- **WHEN** student_b（B 班）调用 `GET /api/wrong-questions`，A 班已有错题
- **THEN** 返回空数组，不泄露任何 A 班数据

#### Scenario: 跨班详情同构 404

- **WHEN** student_b 查询 A 班错题 id=5，再查询不存在 id=99999
- **THEN** 两次响应均为 404 + `{"error":"not found"}`，body 完全一致

#### Scenario: 学生跨他人详情 404

- **WHEN** 同班另一学生查询不属于自己的错题 id
- **THEN** 返回 404，不泄露「这条错题属于别人」这一事实

#### Scenario: 未登录被拒

- **WHEN** 未携带 Bearer 令牌调用任一 wrong-questions 端点
- **THEN** 返回 401

### Requirement: 错题讲解对话

系统 SHALL 提供 `POST /api/wrong-questions/<int:id>/explain` 端点，在指定错题上触发讲解对话；服务端 MUST 创建一条新会话（绑定本班默认启用助手），把错题的 question/student_answer/reference_answer/reason 作为用户消息注入，返回 SSE 流；学生只能触发自己的，教师可触发本班的，跨班/跨他人 MUST 404。

#### Scenario: 学生触发自己的讲解

- **WHEN** student_a 对自己的错题 id=5 调用 explain
- **THEN** 创建一条 conversation（归属 student_a），返回 `text/event-stream`，流中包含 delta 事件；messages 表写入一条 user 消息含题目与参考答案

#### Scenario: 教师触发本班讲解

- **WHEN** teacher_a 对本班任一错题调用 explain
- **THEN** 与学生触发等效，返回 SSE 流

#### Scenario: 学生触发他人错题被拒

- **WHEN** student_b 对 student_a 的错题调用 explain
- **THEN** 返回 404，不创建会话，不写消息

#### Scenario: 不存在 id 触发被拒

- **WHEN** 任意用户对不存在的 wrong_question id 调用 explain
- **THEN** 返回 404 + `{"error":"not found"}`
