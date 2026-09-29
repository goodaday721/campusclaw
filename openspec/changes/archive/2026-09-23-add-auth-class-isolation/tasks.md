## 1. 项目脚手架与依赖

- [x] 1.1 初始化 Python 项目：`requirements.txt`、`.gitignore`、`.env.example`（含 `JWT_SECRET`、`DATABASE_PATH`、`PORT`），验证 `pip install -r requirements.txt` 成功
- [x] 1.2 安装依赖：`flask`、`sqlite3`（标准库）或 `sqlalchemy`、`bcrypt`、`pyjwt`、`werkzeug`（随 Flask）、`python-dotenv`、`pydantic`；验证 `python -c "import flask, jwt, bcrypt"` 可加载
- [x] 1.3 建立目录结构：`app/{config,routes,middleware,db,repositories,services,utils}`、`migrations/`、`seeds/`；验证目录与空入口文件存在

## 2. 数据库与迁移

- [x] 2.1 编写迁移建表：`classes`、`users(id, username UNIQUE, password_hash, role CHECK IN ('teacher','student'), class_id)`、`materials(id, class_id, uploader_user_id, filename, storage_key, mime, size, created_at)`；验证迁移在干净 SQLite 上执行成功
- [x] 2.2 建索引：`users(class_id)`、`materials(class_id)`；验证 `EXPLAIN QUERY PLAN` 走索引
- [x] 2.3 种子脚本预置 2 个班级、2 名教师（分属 A/B 班）、2 名学生（A/B 班），密码用 bcrypt(cost≥12) 哈希；验证 `select` 返回预期记录且 `password_hash` 非明文
- [x] 2.4 种子脚本幂等：用 `INSERT OR IGNORE` 或先查后插，重复执行不产生重复记录；验证连续两次执行后 `select count(*)` 一致且无重复用户名

## 3. 配置与启动校验

- [x] 3.1 实现 `app/config.py`：从 `os.environ` 读取 `JWT_SECRET`、`DATABASE_PATH`、`PORT`、上传上限与 MIME 白名单；验证缺 `JWT_SECRET` 或 `DATABASE_PATH` 时启动函数抛错并打印明确信息
- [x] 3.2 实现 app 启动入口：校验必需环境变量 → 失败则 `sys.exit(1)` 不监听端口；成功则连 SQLite、跑迁移/种子（首次）、监听端口；验证缺失环境变量时端口无监听

## 4. 认证（user-auth）

- [x] 4.1 实现 `POST /auth/login`：校验用户名密码（`bcrypt.checkpw`），成功用 PyJWT 签发 JWT（含 `sub`、`role`、`classId`、`exp`），失败返回统一 401 不区分用户/密码错误；验证三条场景测试通过（成功、密码错、用户不存在）
- [x] 4.2 实现 `auth_required` 装饰器：解析 JWT 注入 `g.current_user`，无效/缺失时对 API 返回 401 JSON、对页面请求（`Accept: text/html`）302 到 `/login?next=<path>`；验证 API 与页面分支测试通过
- [x] 4.3 验证日志不输出明文密码：覆盖登录失败/异常路径，断言日志不含提交密码字段

## 5. 角色鉴权（role-access）

- [x] 5.1 实现 `role_required(role)` 装饰器：基于 `g.current_user.role` 放行或返回 403；验证学生调用上传返回 403、教师放行测试通过
- [x] 5.2 集成测试：学生绕过前端用工具直接带自己 JWT 调用 `POST /materials` 仍返回 403；验证拦截不依赖前端

## 6. 班级隔离（class-isolation）

- [x] 6.1 实现 `MaterialsRepository`：提供 `find_by_class(classId)` 与 `find_by_id_scoped_to_class(id, classId)`，禁止裸 `find_by_id`；验证 repository 单测覆盖按班级过滤
- [x] 6.2 集成测试：A 班用户 `GET /materials` 仅返回 A 班记录；A 班用户 `GET /materials/{B班材料id}` 返回 404/403；教师跨班访问同样被拒；验证四条场景测试通过
- [x] 6.3 验证服务端过滤不可绕过：直接构造 URL 越权访问 `GET /materials/{id}` 仍按 JWT `classId` 过滤后 404/403

## 7. 知识库材料（knowledge-materials）

- [x] 7.1 实现 `POST /materials`：Werkzeug 上传（`request.files`）→ 文件落盘到 `uploads/materials/<classId>/<uuid>/<filename>` → 写入 `materials` 记录，`class_id` 取 `g.current_user.classId`（忽略请求体 `classId`）→ 返回 201 与新记录；验证教师上传成功、记录归属令牌班级、客户端声明班级被忽略三条测试通过
- [x] 7.2 实现 `GET /materials`：调 `find_by_class(g.current_user.classId)` 返回本班列表；验证学生与教师均可读取本班、上传后列表含新记录
- [x] 7.3 加上传约束：大小上限（如 50MB）与 MIME 白名单，超限/非法类型返回 4xx；验证超限与非法类型被拒绝测试通过

## 8. 运行时契约（app-runtime）

- [x] 8.1 实现 `GET /health`：无认证，SQLite 连通返回 200 `{"status":"ok"}`，不通返回 503；验证成功与 DB 不可用降级测试通过，并断言响应不含密钥/用户/材料数据
- [x] 8.2 编写 `docker-compose.yml`：仅 `app` 一服务（SQLite 文件数据库，挂卷持久化 DB 文件与 `uploads/`），环境变量正确；验证 `docker compose up` 后 `curl http://localhost:${PORT}/health` 返回 200
- [x] 8.3 验证 `.env.example` 覆盖全部必需变量且源码/仓库内无硬编码密钥或连接串（grep 检查）

## 9. 最小前端验证页面

- [x] 9.1 提供极简登录页 `GET /login`（接受用户名密码 → 调 `/auth/login` → 存 JWT → 回到 `next`）与一个受保护页 `GET /me`（展示当前用户）；验证未登录访问 `/me` 跳转登录、登录后回到 `/me`

## 10. 端到端验收

- [x] 10.1 端到端脚本：`docker compose up` 后依次跑——健康检查 200、教师登录、教师上传、教师/学生看本班列表含新记录、学生上传 403、A 班访问 B 班材料 404/403、重复启动后预置数据不重复；验证全部断言通过
- [x] 10.2 跑 `openspec validate --strict --change add-auth-class-isolation` 通过，并对照各 spec 场景逐一核对实现覆盖
