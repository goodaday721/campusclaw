## Purpose

区分教师与学生角色，并在服务端按角色强制授权；学生调用材料上传接口必须被服务端拒绝，教师才能写入知识库材料。

## ADDED Requirements

### Requirement: 角色区分与令牌携带

系统 SHALL 在用户记录与 JWT 中携带 `role` 字段，取值为 `teacher` 或 `student`；鉴权决策 MUST 基于服务端解析的令牌声明，而非客户端自报角色。

#### Scenario: 令牌声明角色
- **WHEN** 用户登录成功
- **THEN** 签发的 JWT `role` 声明与数据库用户记录的 `role` 一致

### Requirement: 学生不能上传材料

系统 MUST 在 `POST /materials` 上传接口的服务端鉴权层拒绝 `role=student` 的请求，返回 403；该拦截 MUST NOT 依赖前端隐藏按钮或客户端判断。

#### Scenario: 学生调用上传被拒绝
- **WHEN** 已登录的 `role=student` 用户携带有效 JWT 调用 `POST /materials`
- **THEN** 系统返回 403 且不写入任何知识库材料记录

#### Scenario: 教师调用上传被接受
- **WHEN** 已登录的 `role=teacher` 用户携带有效 JWT 调用 `POST /materials`
- **THEN** 系统继续进入材料写入流程

### Requirement: 角色断言在服务端强制

任何角色相关的放行或拒绝 MUST 在服务端中间件或路由守卫中完成；前端 UI 可作辅助性展示，但移除或绕过前端控制 MUST NOT 改变服务端的拒绝结果。

#### Scenario: 绕过前端直接调用被拒
- **WHEN** 学生不经过前端 UI，直接用工具携带自己的 JWT 调用 `POST /materials`
- **THEN** 服务端仍返回 403
