## Purpose

让教师与学生通过账号密码登录建立会话，未登录访问受保护资源时被引导到登录页，并强制密码以单向哈希存储、JWT 密钥只来自服务端环境变量。

## ADDED Requirements

### Requirement: 账号密码登录

系统 SHALL 提供 `POST /auth/login` 接口，接受用户名与密码；凭据有效时返回 JWT 会话凭证，凭据无效时返回 401 且不泄露用户是否存在。

#### Scenario: 教师凭据有效登录成功
- **WHEN** 教师用正确用户名与密码调用 `POST /auth/login`
- **THEN** 系统返回 200 与包含 `userId`、`role=teacher`、`classId` 的 JWT

#### Scenario: 密码错误登录失败
- **WHEN** 用户使用存在的用户名但错误密码调用 `POST /auth/login`
- **THEN** 系统返回 401 与统一错误信息，且不提示“用户不存在”或“密码错误”之间的区别

#### Scenario: 不存在的用户登录失败
- **WHEN** 用户使用不存在的用户名调用 `POST /auth/login`
- **THEN** 系统返回 401 与和密码错误完全相同的错误信息

### Requirement: 未登录访问受保护资源被引导到登录

系统 SHALL 对未携带有效会话凭证的受保护页面/接口请求返回 401；对浏览器页面请求 SHALL 以重定向到登录页作为引导，对 API 请求 SHALL 返回 401 JSON。

#### Scenario: 未登录访问受保护 API
- **WHEN** 未携带有效 JWT 的请求访问 `POST /materials`
- **THEN** 系统返回 401 且不执行任何写入操作

#### Scenario: 未登录浏览器访问受保护页面
- **WHEN** 未携带有效会话的浏览器请求访问受保护页面
- **THEN** 系统以 302 重定向到登录页并在登录成功后回到原页面

### Requirement: 密码必须哈希存储

系统 MUST 以单向自适应哈希（bcrypt 或 argon2）存储用户密码；明文密码 MUST NOT 出现在数据库、日志、错误信息或可观测输出中。

#### Scenario: 数据库中不存明文密码
- **WHEN** 用户注册或重置密码
- **THEN** 数据库用户表对应记录的密码字段为哈希值，无法反推出明文

#### Scenario: 日志不泄露明文
- **WHEN** 登录失败或系统异常被记录
- **THEN** 日志内容不含提交的明文密码

### Requirement: JWT 密钥只来自服务端环境变量

系统 MUST 从服务端环境变量读取 JWT 签名密钥；密钥 MUST NOT 硬编码在源码、提交进仓库或下发给客户端。

#### Scenario: 缺失密钥环境变量时拒绝启动
- **WHEN** 服务启动时未配置 JWT 密钥环境变量
- **THEN** 服务进程退出并以错误日志说明密钥缺失，不监听任何端口
