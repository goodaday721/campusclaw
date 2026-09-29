## Purpose

让教师与学生通过账号密码登录建立服务端会话（HttpOnly Cookie），未登录访问受保护资源时被引导到登录页，并强制密码以单向哈希存储、会话标识仅存于服务端 sessions 表。

## Requirements

### Requirement: 账号密码登录

系统 SHALL 提供 `POST /auth/login` 接口，接受用户名与密码；凭据有效时 MUST 校验密码哈希、作废浏览器携带的旧会话标识、写入新的 `sessions` 记录并通过 `Set-Cookie` 下发新的随机会话标识（HttpOnly、SameSite），Cookie 中 MUST NOT 携带角色、班级或口令等任何业务信息；凭据无效时返回 401 且各失败原因（用户不存在、密码错误）对外响应完全一致。

#### Scenario: 教师凭据有效登录成功
- **WHEN** 教师用正确用户名与密码调用 `POST /auth/login`
- **THEN** 系统返回 200，`Set-Cookie` 下发新的随机会话标识（HttpOnly），`sessions` 表新增一条指向该教师、含过期时间的记录

#### Scenario: 登录成功换发会话标识
- **WHEN** 浏览器携带已存在的会话标识调用 `POST /auth/login` 且凭据有效
- **THEN** 系统签发全新会话标识下发，旧会话标识对应的会话记录立即作废，旧标识后续请求返回 401

#### Scenario: 密码错误登录失败
- **WHEN** 用户使用存在的用户名但错误密码调用 `POST /auth/login`
- **THEN** 系统返回 401 与统一错误信息，且不提示"用户不存在"或"密码错误"之间的区别

#### Scenario: 不存在的用户登录失败
- **WHEN** 用户使用不存在的用户名调用 `POST /auth/login`
- **THEN** 系统返回 401 与和密码错误完全相同的错误信息

### Requirement: 未登录访问受保护资源被引导到登录

系统 SHALL 对未携带有效会话 Cookie 的受保护页面/接口请求返回 401；对浏览器页面请求 SHALL 以重定向到登录页作为引导，对 API 请求 SHALL 返回 401 JSON。

#### Scenario: 未登录访问受保护 API
- **WHEN** 未携带有效会话 Cookie 的请求访问 `POST /materials`
- **THEN** 系统返回 401 且不执行任何写入操作

#### Scenario: 未登录浏览器访问受保护页面
- **WHEN** 未携带有效会话的浏览器请求访问受保护页面
- **THEN** 系统以 302 重定向到登录页并在登录成功后回到原页面

### Requirement: 每次请求从服务端会话解析身份

系统 SHALL 在每次受保护请求中读取会话 Cookie，到 `sessions` 表校验会话存在且未过期，并从 `users` 表读取该用户的角色与班级；过期或不存在的会话 MUST 返回 401；角色与班级 MUST 以服务端数据库记录为准，Cookie 与请求参数中的角色、班级声明 MUST 被忽略。

#### Scenario: 会话过期后访问被拒
- **WHEN** 携带已过会话过期时间的会话 Cookie 调用受保护接口
- **THEN** 系统返回 401，且该会话不再可用

#### Scenario: 会话中的身份随用户记录实时生效
- **WHEN** 会话有效期间服务端用户记录的角色或班级发生变化
- **THEN** 后续请求以变更后的数据库记录为准，而非登录时快照

### Requirement: 登出立即失效

系统 SHALL 提供登出能力，登出时 MUST 删除服务端对应的会话记录并清除浏览器 Cookie；登出后原会话标识 MUST 立即失效，后续使用该标识的请求返回 401。

#### Scenario: 登出后会话立即失效
- **WHEN** 已登录用户调用登出接口后，立即携带原会话 Cookie 调用受保护接口
- **THEN** 系统返回 401，且 `sessions` 表中不再存在该会话记录

### Requirement: 密码必须哈希存储

系统 MUST 以单向自适应哈希（bcrypt 或 argon2）存储用户密码；明文密码 MUST NOT 出现在数据库、日志、错误信息或可观测输出中。

#### Scenario: 数据库中不存明文密码
- **WHEN** 用户注册或重置密码
- **THEN** 数据库用户表对应记录的密码字段为哈希值，无法反推出明文

#### Scenario: 日志不泄露明文
- **WHEN** 登录失败或系统异常被记录
- **THEN** 日志内容不含提交的明文密码
