## Purpose

把班级作为数据边界，在服务端查询层强制过滤，确保 A 班用户访问 B 班材料被拒绝，杜绝跨班越权读取。

## ADDED Requirements

### Requirement: 班级作用域绑定用户

系统 SHALL 为每个用户绑定其所属 `classId`，并在 JWT 中携带该 `classId`；班级归属 MUST 来自服务端用户记录，不接受客户端请求参数中的班级声明。

#### Scenario: 令牌携带班级
- **WHEN** 用户登录成功
- **THEN** 签发的 JWT 包含与服务端用户记录一致的 `classId`

### Requirement: 跨班访问被服务端拒绝

系统 MUST 在查询层按当前用户 `classId` 过滤；用户访问非本班材料时 MUST 返回 404 或 403，且不返回任何非本班数据。该过滤 MUST 在数据库查询条件或 ORM 作用域中强制，不依赖前端隐藏按钮。

#### Scenario: A 班用户请求 B 班材料列表
- **WHEN** A 班用户携带有效 JWT 调用 `GET /materials`
- **THEN** 返回结果仅含 A 班材料，不包含任何 B 班记录

#### Scenario: A 班用户直接请求 B 班材料详情
- **WHEN** A 班用户携带有效 JWT 调用 `GET /materials/{id}`，且该材料属于 B 班
- **THEN** 系统返回 404 或 403，不返回材料内容

#### Scenario: 教师也只能访问本班
- **WHEN** 教师携带有效 JWT 调用 `GET /materials/{id}`，且该材料属于其所属班级之外的班级
- **THEN** 系统返回 404 或 403

### Requirement: 班级过滤在服务端强制

任何班级作用域过滤 MUST 在服务端查询层完成；前端 UI 隐藏或不可见 MUST NOT 是唯一的隔离手段，移除前端控制 MUST NOT 导致跨班数据可见。

#### Scenario: 直接构造 URL 越权访问
- **WHEN** 用户不经过前端 UI，直接用工具构造非本班材料 ID 调用 `GET /materials/{id}`
- **THEN** 服务端按其 JWT `classId` 过滤后仍返回 404 或 403
