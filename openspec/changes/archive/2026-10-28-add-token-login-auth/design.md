# Design: add-token-login-auth

## Context

第 2 课把课程原型的 JWT 认证改成了服务端会话 Cookie（HttpOnly/SameSite），换取"身份实时生效""登出立即失效""会话固定防御"三条强属性。老师现要求把认证改回 token 方案：原型以 `Authorization: Bearer <HS256 JWT>` 调用接口，payload 含 user_id/role/class_id/iat，作业验收证据是 DevTools 中的 Bearer 请求头。系统为 Flask + MySQL + Compose 四服务单实例部署，规约驱动开发。

## Goals / Non-Goals

- Goals：登录签发 JWT、全部受保护接口走 Bearer 头、登出即失效、身份实时生效、前端 token 化、测试与 e2e 同步。
- Non-Goals：refresh token、OAuth/SSO、无状态化、多设备管理、CSRF 设施、密码找回。详见 proposal Non-Goals。

## Decisions

### D1：JWT + 服务端会话记录的混合方案（核心决策）

纯无状态 JWT 有两个与现有规约冲突的问题：无法即时撤销（登出后 token 在 exp 前仍有效）、身份快照陈旧（role/class 变更不影响已签发 token）。因此采用混合方案：**JWT 只作为认证载体（防篡改的用户标识信封），会话状态仍在服务端**：

- payload 仅 `{sub, jti, iat, exp}`，与原型（内嵌 role/class_id）刻意不同——身份每请求从 `users` 表实时读取，规约"会话中的身份随用户记录实时生效"原样保留，且 token 泄露不暴露业务字段。
- 撤销 = 删除 `sessions` 表中 jti 行，规约"登出立即失效"原样保留。
- 代价：每次受保护请求多一次 `sessions` 主键查询（与现方案持平，无回归）；重复登录签发的新旧 token 在有效期内并存（原方案"登录换发作废旧会话"不再可行——Bearer 方案下服务端在登录时无法得知客户端旧 token；规约场景已改为"重复登录签发互不相同的 token"）。

### D2：Token 形态与库

- HS256 + PyJWT（`PyJWT>=2.9,<3.0`，成熟、API 稳定、无额外系统依赖）。
- `exp = iat + SESSION_TTL_HOURS`（复用 24h 时效配置，不新增 TTL 变量）。
- `jti = uuid4().hex`（32 字符，`sessions.id VARCHAR(128)` 主键直接容纳，**零迁移**）。
- 验证失败（签名错/过期/格式坏）统一抛 `TokenInvalid`，对外一律 401，不泄露失败细节。

### D3：复用 sessions 表与仓库层

`sessions` 表语义从"opaque 会话标识"变为"JWT jti 登记簿"，表结构不变；`sessions_repo.find_valid()`（按 id 查 + 过期过滤 + JOIN users）与 `delete()` 原样复用；`create()` 改为接受调用方传入的 `jti` 与 `expires_at`（token 服务负责生成）。下游所有 `g.current_user` 消费方（role 校验、班级隔离、materials/search/ask）零改动。

### D4：前端策略

- token 存 `localStorage`（方案本身要求 JS 持有 token，HttpOnly Cookie 不可行）。XSS 权衡：页面为单文件内联 JS、无第三方脚本注入点，且各接口输出均转义；风险与课程原型一致。
- 统一 `api(path, opts)` 封装：自动附加 `Authorization: Bearer`；401 时清 token 跳 `/login`。
- `/dashboard` 页面改为公开外壳 + 前端守卫（页面导航请求无法携带 Authorization 头，服务端装饰器必须移除，否则永远 302）。
- `<a href>` 直链下载/打开材料改为 fetch→blob→objectURL（下载）与 blob 新标签页打开（查看），材料均为 `.txt`/`.md` 文本，无需处理二进制流。

### D5：配置与密钥

- `JWT_SECRET` 为启动必需项（`config._require` 强制），随机生成写入本地 `.env`；`.env.example` 只给占位与说明。
- 删除 `SESSION_COOKIE_NAME`（连同 cookie 会话语义一次性移除，不做双方案并存——并存会让规约与测试语义含混）。

### D6：测试策略

- conftest 登录 fixture 改为：登录拿 token → `BearerClient` 包装 Flask test client，自动为每个请求注入 Authorization 头——其余测试文件的 `client.get/post` 调用形态不变，零改动。
- `test_auth.py` 重写：三段式 token、无 Set-Cookie、payload 可 base64 解出且不含角色/口令、错密码/不存在用户 401 一致、过期/篡改/登出后复用 401、实时身份（改库后下一请求生效）。
- e2e 两种模式同步 token 化；HTTP 模式以 `opener.addheaders` 携带 Bearer 头。

## Risks / Trade-offs

- **localStorage XSS**：token 可被脚本读取；以页面无第三方脚本、输出转义缓解。若后续引入富文本/第三方 JS，需重评（可回退 HttpOnly Cookie 双轨，超出本变更范围）。
- **旧 token 并存**：重复登录不作废旧 token（Bearer 方案固有限制）；登出即失效与 24h 过期兜底。
- **JWT_SECRET 轮换**：更换密钥会使全部存量 token 失效，所有用户需重新登录（单实例课程场景可接受）。
