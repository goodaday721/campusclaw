## MODIFIED Requirements

### Requirement: 账号密码登录

系统 SHALL 提供 `POST /auth/login` 接口，接受用户名与密码；凭据有效时 MUST 校验密码哈希，签发 HS256 JWT（payload 含用户标识 `sub`、唯一会话标识 `jti`、签发时间 `iat` 与过期时间 `exp`，payload 中 MUST NOT 内嵌角色、班级或口令等任何业务信息），将 `jti` 作为会话记录写入服务端 `sessions` 表（含过期时间），并在响应体中返回 token 与不含口令的用户信息；系统 MUST NOT 通过 `Set-Cookie` 建立会话；凭据无效时返回 401 且各失败原因（用户不存在、密码错误）对外响应完全一致。

#### Scenario: 教师凭据有效登录成功

- **WHEN** 教师用正确用户名与密码调用 `POST /auth/login`
- **THEN** 系统返回 200，响应体包含三段式 JWT 与不含口令的用户信息，`sessions` 表新增一条以该 token 的 `jti` 为主键、含过期时间的记录，响应中不存在 `Set-Cookie` 头

#### Scenario: 登录成功换发会话标识

- **WHEN** 同一用户连续两次成功调用 `POST /auth/login`
- **THEN** 系统两次签发的 token 互不相同（`jti` 不同），且两个 token 在各自有效期内均为有效凭证（多端并存属预期行为）

#### Scenario: 密码错误登录失败

- **WHEN** 用户使用存在的用户名但错误密码调用 `POST /auth/login`
- **THEN** 系统返回 401 与统一错误信息，且不提示"用户不存在"或"密码错误"之间的区别

#### Scenario: 不存在的用户登录失败

- **WHEN** 用户使用不存在的用户名调用 `POST /auth/login`
- **THEN** 系统返回 401 与和密码错误完全相同的错误信息

### Requirement: 未登录访问受保护资源被引导到登录

系统 SHALL 对未携带有效 `Authorization: Bearer` Token 的受保护 API 请求返回 401 JSON；受保护页面 SHALL 作为公开外壳交付，由前端在本地无 token 或受保护 API 返回 401 时重定向到登录页，登录成功后回到原页面。

#### Scenario: 未登录访问受保护 API

- **WHEN** 不带 `Authorization` 头（或 token 无效）的请求访问 `POST /materials`
- **THEN** 系统返回 401 且不执行任何写入操作

#### Scenario: 未登录浏览器访问受保护页面

- **WHEN** 本地未保存 token 的浏览器打开受保护页面（如 `/dashboard`）
- **THEN** 页面外壳正常返回，前端脚本检测到无 token 立即跳转登录页，登录成功并保存 token 后回到原页面

### Requirement: 每次请求从服务端会话解析身份

系统 SHALL 在每次受保护请求中解析 `Authorization: Bearer` 头中的 JWT：使用服务端密钥验证签名（HS256）与有效期，并到 `sessions` 表校验该 token 的 `jti` 存在且未过期（未被登出撤销），随后从 `users` 表读取该用户当前的角色与班级。签名无效、payload 篡改、已过期或会话记录不存在的 token MUST 返回 401；角色与班级 MUST 以服务端数据库记录为准，token payload 与请求参数中的角色、班级声明 MUST 被忽略。

#### Scenario: 会话过期后访问被拒

- **WHEN** 请求携带 `exp` 已过的 token 调用受保护接口
- **THEN** 系统返回 401，且该 token 不再可用

#### Scenario: 篡改或伪造的 token 被拒

- **WHEN** 请求携带签名错误或 payload 被篡改的 token 调用受保护接口
- **THEN** 系统返回 401，不泄露签名验证的失败细节

#### Scenario: 会话中的身份随用户记录实时生效

- **WHEN** token 有效期间服务端用户记录的角色或班级发生变化
- **THEN** 后续请求以变更后的数据库记录为准，而非登录时快照

### Requirement: 登出立即失效

系统 SHALL 提供登出接口；登出时 MUST 删除服务端 `sessions` 表中对应的 `jti` 会话记录；登出后原 token MUST 立即失效，后续使用该 token 的请求返回 401；客户端 SHALL 清除本地存储的 token。

#### Scenario: 登出后会话立即失效

- **WHEN** 已登录用户调用登出接口后，立即携带原 Bearer token 调用受保护接口
- **THEN** 系统返回 401，且 `sessions` 表中不再存在该 token 对应的会话记录
