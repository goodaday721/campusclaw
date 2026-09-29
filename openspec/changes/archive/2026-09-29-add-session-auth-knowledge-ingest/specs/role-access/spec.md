## ADDED Requirements

### Requirement: 角色区分与会话解析

系统 SHALL 在用户记录中维护 `role` 字段，取值为 `teacher` 或 `student`；鉴权决策 MUST 基于服务端会话解析并从数据库用户记录读取的角色，而非客户端自报角色或登录时签发的快照。

#### Scenario: 会话解析出真实角色
- **WHEN** 用户登录成功并携带会话 Cookie 调用受保护接口
- **THEN** 服务端从数据库用户记录读取的角色与该用户实际角色一致

## MODIFIED Requirements

### Requirement: 学生不能上传材料

系统 MUST 在 `POST /materials` 上传接口的服务端鉴权层拒绝 `role=student` 的请求，返回 403；该拦截 MUST 发生在文件落盘与数据表写入之前，MUST NOT 依赖前端隐藏按钮或客户端判断。

#### Scenario: 学生调用上传被拒绝
- **WHEN** 已登录的 `role=student` 用户携带有效会话调用 `POST /materials`
- **THEN** 系统返回 403，磁盘无新文件，materials 与 knowledge_entries 表均无新记录

#### Scenario: 教师调用上传被接受
- **WHEN** 已登录的 `role=teacher` 用户携带有效会话调用 `POST /materials`
- **THEN** 系统继续进入材料写入流程

### Requirement: 角色断言在服务端强制

任何角色相关的放行或拒绝 MUST 在服务端中间件或路由守卫中完成；前端 UI 可作辅助性展示，但移除或绕过前端控制 MUST NOT 改变服务端的拒绝结果。

#### Scenario: 绕过前端直接调用被拒
- **WHEN** 学生不经过前端 UI，直接用工具携带自己的会话 Cookie 调用 `POST /materials`
- **THEN** 服务端仍返回 403

## REMOVED Requirements

### Requirement: 角色区分与令牌携带

**Reason**: 认证由 JWT 改为服务端会话，角色不再写入令牌，而是每次请求从数据库用户记录读取。
**Migration**: 由 ADDED 的"角色区分与会话解析"承接，判定依据由令牌声明改为服务端会话解析。
