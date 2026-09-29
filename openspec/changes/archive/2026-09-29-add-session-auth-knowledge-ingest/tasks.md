## 1. 配置与依赖

- [x] 1.1 `requirements.txt` 移除 PyJWT，确认 `pip install -r requirements.txt` 在干净环境下成功
- [x] 1.2 `app/config.py` 删除 `JWT_SECRET`，新增 `SESSION_TTL_HOURS`（必需）与 `SESSION_COOKIE_NAME`（默认 `session_id`）；`.env.example`、`run.py` 启动校验同步；verify: 缺 `SESSION_TTL_HOURS` 时 `python run.py` 退出码非 0 且错误信息明确

## 2. 数据模型：五张表

- [x] 2.1 新增 `migrations/002_sessions_knowledge.sql`：建 `sessions`（id TEXT PK、user_id 外键级联、expires_at）与 `knowledge_entries`（material_id 外键级联、class_id 租户列非空、content、source，两列均建索引），两表可重复执行；verify: 对已有库连续执行两次迁移无报错、无重复对象
- [x] 2.2 新增 `app/repositories/sessions.py`：create（token_urlsafe 标识 + 过期时间）、find_valid（过期/不存在返回 None）、delete；verify: pytest 单测覆盖创建、过期拒识、删除后拒识
- [x] 2.3 新增 `app/repositories/knowledge.py`：create（material_id、class_id、content、source）；verify: pytest 单测插入后可按 material_id 查回正文
- [x] 2.4 `seeds/seed.py` 补两班标题可区分的示例材料及 knowledge_entries 正文，`INSERT OR IGNORE` 幂等；verify: 种子执行两次后 materials/knowledge_entries 计数不变且两班标题不同

## 3. 会话认证

- [x] 3.1 重写 `app/routes/auth.py`：登录校验哈希后删旧会话行、写新行、Set-Cookie（HttpOnly、SameSite=Lax、Path=/），失败原因对外一致；新增 `POST /auth/logout` 删行清 Cookie；verify: pytest——登录后 Cookie 存在且 DB 有会话行、再次登录换发新标识旧标识 401、登出后原 Cookie 401 且 DB 无行
- [x] 3.2 重写 `app/middleware/auth.py`：读 Cookie → sessions 查有效会话 → JOIN users 取 role/classId 存 `g.current_user`；过期/缺失 401（API）/302（页面）；verify: pytest——无 Cookie 401、过期会话 401、有效会话解析出与 users 表一致的角色班级
- [x] 3.3 `app/routes/pages.py`、`app/__init__.py` 移除全部 JWT 引用；verify: `grep -ri "jwt\|Bearer" app/` 零命中

## 4. 上传入库与下载

- [x] 4.1 新增 `app/services/upload.py`：白名单仅 `.txt`/`.md`、大小上限校验、服务端生成 `<uuid>.<ext>` 存储名落盘、读正文、单事务写 materials + knowledge_entries（同一会话班级值）、失败回滚两表并删文件；verify: pytest——合法上传两表各一条且班级一致、`.pdf` 拒绝且无文件无记录、模拟 DB 失败后文件被清理两表无残留
- [x] 4.2 `app/routes/materials.py` 上传改走服务层，班级取 `g.current_user.classId`，请求体 classId 丢弃；verify: pytest——教师上传 201 且请求体伪造 classId 不影响归属、学生上传 403 且落盘/写库均未发生
- [x] 4.3 `app/routes/materials.py` 新增 `GET /materials/<id>/download`：本班命中返回文件（附件名用 source），跨班/不存在返回与详情同构 404；verify: pytest——本班学生下载内容与上传正文一致、跨班下载 404 且响应体与不存在时相同

## 5. 测试与 E2E 适配

- [x] 5.1 `tests/` 全量从 Bearer 头迁移为 Cookie 会话（conftest 提供登录 fixture）；verify: `pytest` 全部通过
- [x] 5.2 `e2e_test.py` 改用会话 Cookie 流程，断言覆盖：登录换发、上传后两表一致、列表可查、学生 403、跨班 404、下载一致、登出失效；verify: `python e2e_test.py` 全部通过

## 6. Compose 与端到端验收

- [x] 6.1 重建镜像并 `docker compose up`，确认迁移 002 自动执行、种子幂等、`GET /health` 200；verify: `docker compose logs` 无迁移错误，health 返回 ok
- [x] 6.2 执行 `docker compose down` 后 `up`（不带 `-v`），原账号可登录、已传材料可查可下载；verify: down→up 后 materials 列表与下载内容不变
- [x] 6.3 全量场景回归并保留输出记录；verify: `openspec validate --strict --change add-session-auth-knowledge-ingest` 通过，且规约场景逐条执行留痕
