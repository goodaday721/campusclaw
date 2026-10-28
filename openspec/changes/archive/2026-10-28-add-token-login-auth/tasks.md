# Tasks: add-token-login-auth

## 1. 依赖与配置

- [x] 1.1 `requirements.txt` 增加 `PyJWT>=2.9,<3.0`，`.env.example` 增加 `JWT_SECRET=` 占位与说明并删除 `SESSION_COOKIE_NAME`
  - verify: `docker compose build api` 成功；镜像内 `pip show pyjwt` 显示 2.9+
- [x] 1.2 `app/config.py`：`jwt_secret` 必填（缺失拒绝启动），token 有效期复用 `session_ttl_hours`，删除 `session_cookie_name`；本地 `.env` 写入随机 `JWT_SECRET`
  - verify: 去掉 JWT_SECRET 启动 api 容器退出并报明确错误；带上后 `/health` 200

## 2. 后端

- [x] 2.1 新增 `app/services/token_auth.py`：`issue(user_id)` 签发 HS256 JWT（sub/jti/iat/exp，jti=uuid4.hex），`verify(token)` 验签验期返回 payload，失败抛 `TokenInvalid`
  - verify: pytest 单测覆盖签发/验证/过期/篡改四类路径
- [x] 2.2 `app/repositories/sessions.py`：`create` 改为写入调用方传入的 `jti` 与 `expires_at`；`find_valid`/`delete` 复用不变
  - verify: pytest 中 sessions 相关既有用例随 2.1 适配后通过
- [x] 2.3 `app/middleware/auth.py`：改解析 `Authorization: Bearer`；verify → `sessions.find_valid(jti)` → 实时读 users 注入 `g.current_user` 与 `g.token_jti`；无头/无效返回 401（API）或 302（页面）
  - verify: 无 Authorization 头 curl `POST /materials` 返回 401 JSON
- [x] 2.4 `app/routes/auth.py`：login 签发 JWT + jti 入库 + 响应体 `{token, user}`（删除 Set-Cookie 与旧会话作废逻辑）；logout 用 `g.token_jti` 删会话记录；`/auth/me` 保持
  - verify: curl 登录 200 且响应体含三段式 token、无 Set-Cookie；logout 后原 token 再调 `/auth/me` 得 401
- [x] 2.5 `app/__init__.py` 配置注入适配
  - verify: `docker compose up -d api` 后 `/health` 200

## 3. 前端（app/routes/pages.py 内联 JS）

- [x] 3.1 统一 `api()` 封装（自动 Bearer 头 + 401 清 token 跳登录），登录页存 token 后跳转
  - verify: 浏览器登录后 DevTools Application 中可见 token，Network 中 `/auth/me` 请求带 `Authorization: Bearer eyJ...`
- [x] 3.2 Dashboard 改造：`/auth/logout`、materials 列表/上传、reindex、`/search`、`/ask` 全部走 `api()`；页面公开外壳 + 入口无 token 跳登录
  - verify: 手动登出后回登录页；带 token 刷新 /dashboard 正常加载数据
- [x] 3.3 下载按钮与检索/引用"打开材料"改为 fetch→blob 下载/新标签打开
  - verify: 点击下载得到完整文件内容；检索命中"打开材料"新标签展示正文

## 4. 测试与 e2e

- [x] 4.1 `tests/conftest.py`：登录 fixture 改取响应体 token，`BearerClient` 自动注入认证头
  - verify: 现有 isolation/materials/role/retrieval 用例不改断言通过
- [x] 4.2 `tests/test_auth.py` 重写：三段式 token、无 Set-Cookie、payload 不含角色口令、错凭据 401 一致、过期/篡改/登出复用 401、实时身份
  - verify: `pytest tests/test_auth.py -q` 全过
- [x] 4.3 `e2e_test.py`：test-client 与 HTTP 两模式 token 化，翻转 3 个登录断言（JWT 响应体、无 HttpOnly cookie 断言删除、重复登录 token 互异）
  - verify: 容器内 `python e2e_test.py` 全过；宿主机 `python e2e_test.py --http` 全过

## 5. 文档

- [x] 5.1 README：认证方式改为 JWT Bearer（登录响应示例、请求头示例、JWT_SECRET 说明、登出语义）
  - verify: 按 README"从零启动"步骤在新目录可跑通登录并调用受保护接口

## 6. 验收留痕

- [x] 6.1 全量回归：`docker compose build api && up -d api` → 容器内 pytest 全过 → 容器内 e2e 全过 → 宿主机 HTTP e2e 全过
  - verify: 三组命令退出码均为 0
- [x] 6.2 浏览器取证：登录后 DevTools Network 查看受保护请求的 `Authorization: Bearer eyJ...` 请求头（对照老师样例截图）
  - verify: 截图中请求头含三段式 JWT 且响应 200
- [x] 6.3 `openspec validate add-token-login-auth --strict` 通过，tasks 全部勾选
  - verify: 命令退出码 0
