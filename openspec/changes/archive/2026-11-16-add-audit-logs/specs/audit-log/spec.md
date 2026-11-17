## ADDED Requirements

### Requirement: 审计记录七列

系统 SHALL 把每一次受审计的操作写成 `audit_logs` 的一行，行内 MUST 含七个业务字段：`action`（操作类型）、`target_type`（对象类型）、`target_id`、`actor_id`、`class_id`、`skill_name`（技能标识）、`detail`（用量与耗时等 JSON）。审计行 MUST 按 `class_id` 隔离。

#### Scenario: 登录写入审计

- **WHEN** 用户凭正确密码登录成功
- **THEN** `audit_logs` 新增一行，`action=login`、`target_type=session`、`actor_id` 与 `class_id` 为该用户

#### Scenario: 上传材料写入审计

- **WHEN** 教师上传一份合法材料并返回 201
- **THEN** 新增一行 `action=create`、`target_type=material`、`target_id` 为该材料 id

#### Scenario: 批改写入技能与用量

- **WHEN** worker 完成一次批改
- **THEN** 新增一行 `action=grade`、`target_type=submission`、`skill_name=作业批改`，`detail` 含 `score` 与耗时 `ms`

#### Scenario: 错题讲解写入技能标识

- **WHEN** 学生对本班错题触发讲解并返回 SSE
- **THEN** 新增一行 `action=explain`、`target_type=wrong_question`、`skill_name=错题讲解`

#### Scenario: 审计故障不影响业务

- **WHEN** 审计写入失败（如表不可用）
- **THEN** 业务请求仍返回其正常结果，只额外输出一行 `audit_write_failed` 日志

### Requirement: 审计查询的教师权限与班级隔离

系统 SHALL 提供 `GET /api/audit-logs`，仅教师可访问，且只返回本班审计行；支持 `limit`、`action`、`target_type` 过滤。

#### Scenario: 教师读本班

- **WHEN** 教师调用 `GET /api/audit-logs`
- **THEN** 返回 `{"audit_logs": [...]}`，每行 `classId` 均等于该教师班级

#### Scenario: 跨班不可见

- **WHEN** B 班教师调用审计接口，A 班已有上传审计
- **THEN** 返回的行全部属于 B 班，不含任何 A 班 material 审计

#### Scenario: 学生越权被拒

- **WHEN** 学生调用 `GET /api/audit-logs`
- **THEN** 返回 403

#### Scenario: 未登录被拒

- **WHEN** 未携带 Bearer 令牌调用审计接口
- **THEN** 返回 401

#### Scenario: 未知过滤值被拒

- **WHEN** 调用 `GET /api/audit-logs?action=nope`
- **THEN** 返回 400 与可读错误，不执行查询

#### Scenario: 上限收敛

- **WHEN** 调用 `GET /api/audit-logs?limit=9999`
- **THEN** 返回 200，最多 200 行
