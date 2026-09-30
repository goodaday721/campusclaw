# Proposal: add-token-login-auth

## Why

老师在第 4 课后新增要求：登录认证改用 token 方案，并以课程原型为样例——登录后前端以 `Authorization: Bearer <JWT>` 请求头调用全部接口（DevTools Network 中可见 `Authorization: Bearer eyJ...` 三段式 JWT）。当前系统实现的是第 2 课确定的服务端会话 HttpOnly Cookie 方案：登录签发随机 opaque token 存 `sessions` 表并 `Set-Cookie`，浏览器凭 Cookie 认证。这与作业验收证据（请求头中的 Bearer JWT）不一致，需要把认证载体从 Cookie 会话切换为 JWT Bearer Token。

## What Changes

- 登录 `POST /auth/login` 改为签发 **HS256 JWT**：payload 仅含 `sub`（用户标识）、`jti`（唯一会话标识）、`iat`、`exp`，MUST NOT 内嵌角色、班级或口令；jti 写入现有 `sessions` 表（复用表结构，`id` 即 jti，无需新迁移）；响应体返回 `{token, user}`，**不再 Set-Cookie**。
- 所有受保护接口改由 `Authorization: Bearer` 头认证：中间件完成签名验证（服务端 `JWT_SECRET`）与有效期验证后，按 jti 查 `sessions` 表确认未撤销，再 JOIN `users` 读取实时角色与班级（保留"身份实时生效"属性；payload 中的角色/班级声明即使存在也被忽略）。
- 登出 `POST /auth/logout` 删除服务端 jti 会话记录；登出后原 token 立即失效（复用返回 401），前端清除本地存储。
- 前端（Dashboard/登录页内联 JS）改用 token 方案：token 存 `localStorage`，统一 `api()` 封装自动附加 Bearer 头；无 token 或 API 返回 401 时跳转登录页；下载材料与"打开材料"由 `<a href>` 改为 fetch→blob（浏览器导航请求无法携带 Authorization 头）。
- **BREAKING**：移除 Cookie 会话方案。`SESSION_COOKIE_NAME` 配置删除；客户端必须以 Bearer 头访问全部受保护接口。
- 新增必需环境变量 `JWT_SECRET`（HS256 签名密钥，仅存服务端 `.env`，启动缺失即拒绝启动）；token 有效期复用现有 `SESSION_TTL_HOURS`（24 小时）。
- `requirements.txt` 新增 `PyJWT>=2.9,<3.0`。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `user-auth`: 认证载体由 HttpOnly Cookie 会话切换为 Bearer JWT；登录响应、请求认证、登出失效、未登录引导四条需求的语义更新；密码哈希要求不变。
- `app-runtime`: 敏感配置范围扩展——`JWT_SECRET` 成为启动必需环境变量（缺失拒绝启动）。

## Non-Goals

- 不做 refresh token 与静默续期；token 过期后重新登录。
- 不做 JWT 无状态化：保留服务端 `sessions` 记录以支持即时撤销（换取"登出立即失效"与"身份实时生效"）。
- 不做 OAuth/SSO/第三方登录与找回密码。
- 不做多设备会话管理界面（重复登录产生的新旧 token 在有效期内并存，属预期行为）。
- 不引入 CSRF 防护设施（Bearer 头方案不依赖浏览器自动附带凭据，天然免疫传统 CSRF）。
- 不改动密码哈希、班级隔离、材料上传、检索与问答等既有行为。

## Impact

- **应用层**：`app/middleware/auth.py`（Bearer 解析）、`app/routes/auth.py`（签发/登出）、`app/repositories/sessions.py`（jti 写入）、新增 `app/services/token_auth.py`（JWT 签发与验证）、`app/config.py`（jwt_secret 必填、删 session_cookie_name）、`app/__init__.py`（配置注入）。
- **前端**：`app/routes/pages.py` 内联 JS 全面改造（token 存储、api() 封装、blob 下载、前端守卫）。
- **配置**：`.env`/`.env.example` 增 `JWT_SECRET`、删 `SESSION_COOKIE_NAME`；`requirements.txt` 增 PyJWT。
- **测试**：`tests/conftest.py`（BearerClient 注入认证头）、`tests/test_auth.py`（JWT 断言重写）、`e2e_test.py`（两种模式 token 化）；其余用例依赖 fixture 应零改动。
- **文档**：README 认证方式说明更新。
- **数据层**：无新迁移（复用 `sessions` 表）。
