# 安全开发规范

适用范围：认证、授权、输入输出、密钥与出站调用。默认拒绝，逐资源授权。

## 默认拒绝与逐资源授权

- 匿名白名单只有：`/health`、`/health/ready`、`/login`、`/dashboard`、`/`、`/me`、`/openapi.json`、`/swagger/index.html`；其余端点一律挂 `@auth_required`。
  检查：`grep -rn "@.*_bp.route" app/routes` 与 `grep -rn "auth_required" app/routes` 逐条比对，白名单外无漏挂。
- 教师专属写操作必须再挂 `@role_required("teacher")`，学生一律 403，且拦截发生在落盘与写库之前；学生可写的只有会话创建与消息发送（`/api/conversations`），靠 `find_owned` 做归属校验。
  检查：`tests/test_role.py::TestRoleRequired`、`tests/test_role.py::TestBypassFrontend`、`tests/test_mcp.py::TestRegistryAPI::test_student_forbidden_everywhere`。
- 路由层按 id 的资源读取必须走带作用域的查询：`materials.find_by_id_scoped_to_class`、`mcp.find(server_id, class_id)`、`conversations.find_owned(conversation_id, user_id, class_id)`；`materials` 刻意不提供裸 `find_by_id`（见其模块注释）。仅按 id 的跟进写入（`mcp.set_status`、`mcp.delete`、`skills.update`、`skills.delete`、`sessions.delete`）只能在该归属查询通过之后执行。
  检查：`grep -rn "find_owned\|find_by_id_scoped_to_class\|mcp.find(" app/routes` 覆盖全部按 id 读取；`grep -n "find_by_id(id)" app/repositories/materials.py` 仅出现在注释。
- 跨班访问返回与不存在完全同构的 404，不用 403/409 暗示资源归属。
  检查：`tests/test_isolation.py::TestCrossClassRejection`、`tests/test_isolation.py::TestDirectURLBypass`。
- 检索类接口跨班表现为 200 + 空命中 + 固定文案，不返回 403/404。
  检查：`tests/test_retrieval.py::TestSearchClassIsolation`。

## 密钥外置与轮换

- `.env` 不入版本库（`.gitignore` 已列 `.env`），`.env.example` 只写键名、占位值与生成命令，不写真实密钥。
  检查：`git check-ignore -v .env` 有输出；`grep -n "API_KEY=\|JWT_SECRET=\|MCP_AUTH_TOKEN=" .env.example` 值均为空或 `change-me`。
- `JWT_SECRET` 轮换的后果写死在流程里：更换后所有已签发 token 立即失效，用户需重新登录。
  检查：`grep -n "JWT_SECRET" .env.example README.md` 均含失效说明；`tests/test_auth.py::TestAuthRequired`。
- `MCP_AUTH_TOKEN` 轮换需两步：改 `.env` 并重建 mcp-demo，同时在教师页重登记该服务器令牌；旧令牌调用会 401 并落 `error` 审计。
  检查：`docker compose up -d --force-recreate mcp-demo` 后 `connect` 失败返回 502；`tests/test_mcp.py::TestMcpServerProtocol`。
- 密钥只出现在服务端内存与 `.env`；API 响应只允许 `hasToken` 布尔值，日志与异常信息不含密钥。
  检查：`tests/test_auth.py::TestNoPlaintextLogs`、`tests/test_mcp.py::TestRegistryAPI::test_seed_registered_has_token_only`（断言响应 JSON 无 `token` 字段）。

## 输入校验与输出转义

- 前端把服务端数据（文件名、摘录、回答、工具文本）写入 `innerHTML` 前必须经 `escapeHtml`。
  检查：`grep -n "innerHTML" app/routes/pages.py` 每处拼接变量都出现 `escapeHtml`；对应 `escapeHtml` 定义在同文件。
- 后端不信任请求体：`class_id`、`role` 被忽略，客户端构造的 `system` 消息被丢弃。
  检查：`tests/test_retrieval.py::TestSearchClassIsolation`、`tests/test_retrieval.py::TestAsk`。
- 服务端返回给浏览器的错误只给短语，网关原始响应与堆栈不外泄。
  检查：`grep -rn "\"detail\"" app/routes` 除 OpenAPI schema 与审计字段外只出现在 `search.py`、`ask.py`、`api_conversations.py` 的 503 分支。

## 附件与文件读取

- 下载先做业务授权查询（`find_by_id_scoped_to_class`），再按 `storage_key` 解析物理路径；查询为空或文件缺失都返回同构 404。
  检查：`tests/test_materials.py::TestDownload`、`app/routes/materials.py::download_material`。
- 存储文件名由服务端生成（`uuid4` + 扩展名），不使用客户端原始名作为路径；客户端名只存 `filename` 列。
  检查：`grep -n "uuid.uuid4" app/services/upload.py`；`tests/test_materials.py::TestUploadMaterial`。
- 上传白名单只有 `.txt`/`.md`，白名单外 415、超限 413，均不落盘不写库。
  检查：`tests/test_materials.py::TestUploadConstraints`。

## 令牌存放与撤销

- 浏览器令牌存 `localStorage` 的 `cc_token`，请求带 `Authorization: Bearer`；401 时清 token 并跳 `/login`。
  检查：`grep -n "cc_token\|Authorization" app/routes/pages.py`。
- 服务端只存 `sessions.id`（= JWT `jti`）与过期时间；token payload 不含角色、班级；登出删除该行即撤销。
  检查：`migrations/002_sessions_knowledge.sql` 的 `sessions` 定义；`tests/test_auth.py::TestLogout`。
- 登录失败（用户不存在与密码错误）对外响应完全一致，且用等成本的哈希比对避免时序差异。
  检查：`tests/test_auth.py::TestLogin`、`app/routes/auth.py` 的 `_DUMMY_HASH`。

## 出站地址白名单

- 出站只允许两类目标：课程模型网关（`EMBED_BASE_URL` / `CHAT_BASE_URL`）与 Compose 内网 `http://mcp-demo:8090`。
  检查：`grep -n "_BASE_URL\|mcp-demo" .env.example` 与 `seeds/seed.py::SEED_MCP_SERVER`。
- 教师登记的 `base_url` 目前只校验 `http://` / `https://` 前缀，无 SSRF 黑名单；评审时须人工确认目标属内网或课程网关，登记公网地址一律驳回。
  检查：`tests/test_mcp.py::TestRegistryAPI`（非法前缀 400）；人工核对 `GET /api/mcp/servers` 返回的 `baseUrl`。
- 浏览器不得直连向量库或模型网关：api 与 qdrant 无宿主机端口，网关密钥只在服务端环境变量。
  检查：`docker compose config` 中 api/qdrant 无 `published`；`curl http://localhost:8080/openapi.json` 响应无 key 字段。
