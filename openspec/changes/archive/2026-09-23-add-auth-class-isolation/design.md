
## Context

当前仓库除 OpenSpec 脚手架外无任何应用代码，本变更属全新搭建。技术栈已定为 Flask + SQLite。安全约束来自需求：密码单向哈希、JWT 密钥仅来自服务端环境变量、班级隔离在服务端强制、Docker Compose 启动、`GET /health` 暴露存活状态。需求动机见 `proposal.md` 的 Why 节，行为契约见各 `specs/<capability>/spec.md`。

## Goals / Non-Goals

**Goals:**
- 建立最小可用的认证、角色、班级隔离、知识库材料闭环，可通过 `docker compose up` 一键启动并通过健康检查。
- 让安全边界（密码哈希、密钥来源、班级过滤、角色拒绝）在服务端强制，前端 UI 仅作辅助。
- 让代码结构与数据模型便于后续扩展（如班级管理、作业、通知等）。

**Non-Goals:**
- 不实现注册/找回密码自助流程（初始账号由迁移/种子脚本预置）。
- 不实现细粒度资源级权限（如单条材料的分享、协作者）。
- 不实现文件内容解析、全文检索、预览渲染等材料增强能力。
- 不做多租户/多学校隔离，仅在本项目单实例范围内做班级隔离。
- 不实现前端框架工程化（仅最小登录页与受保护页面示意，足以验证未登录跳转即可）。

## Decisions

### D0：技术栈选型（Flask + SQLite 为主）

- 选择：后端用 Flask + SQLite 实现本变更。
- 理由：Flask 蓝图与装饰器等价表达 `auth_required`→`role_required`→视图的分层鉴权与班级过滤；SQLite 单文件、零独立进程，`docker compose up` 只需一个 app 服务即可启动，最契合"最小闭环 + 一键启动"目标。
- 备选：Node.js + Express + PostgreSQL。生态成熟、并发与约束更强，但需独立数据库进程与 Compose 多服务，对最小闭环过重；spec 的行为契约不绑死框架，可在后续阶段等价替换。
- 失效：若后续切到 Express + PostgreSQL，只需替换数据访问层与启动脚本，spec 的 Requirement 与 Scenario 无需改动。

### D1：会话凭证用 JWT，密钥来自环境变量

- 选择：登录成功用 PyJWT 签发 JWT，声明 `sub=userId`、`role`、`classId`、`iat`、`exp`；签名密钥 `JWT_SECRET` 仅来自 `os.environ`。
- 理由：无服务端会话存储负担，水平扩展简单；与"密钥只放服务端环境变量"约束直接对齐。
- 备选：服务端会话 + Cookie。未选，因需额外会话存储与失效机制，对最小闭环过重；但会话可注销是已知折中（见 Risks）。
- 失效：JWT 设较短 `exp`（如 8h）；后续若需主动登出，可加服务端黑名单（非本变更范围）。

### D2：密码哈希用 bcrypt（自适应 cost）

- 选择：注册/种子脚本用 bcrypt（cost≥12）哈希；登录用 `bcrypt.checkpw`；明文不出现在日志、错误、响应。
- 理由：bcrypt 生态成熟、cost 可调；argon2 更现代但 Python 侧原生绑定依赖更重，bcrypt 足够满足"单向自适应哈希"需求。
- 备选：argon2id。若合规要求更强可在实现阶段替换，spec 不绑死算法（spec 仅要求 bcrypt 或 argon2）。

### D3：数据模型与班级作用域过滤

- 选择：表结构最小化：
  - `users(id, username, password_hash, role, class_id)`
  - `classes(id, name)`
  - `materials(id, class_id, uploader_user_id, filename, storage_key, mime, size, created_at)`
- 选择：班级过滤在数据访问层强制——所有材料查询 MUST 带上当前令牌的 `classId` 作为 WHERE 条件；提供 `MaterialsRepository.find_by_class(classId)` 与 `find_by_id_scoped_to_class(id, classId)`，禁止裸 `find_by_id(id)` 在受保护路由使用。
- 理由：把过滤下沉到查询条件，移除前端控制也无法越权，满足"不靠前端隐藏按钮"与"服务端强制"要求。
- 备选：数据库层强制隔离。PostgreSQL 行级安全（RLS）可作为纵深防御后续加固；SQLite 不支持 RLS，当前阶段以应用层强过滤为唯一权威来源，避免双重维护与测试复杂度。

### D4：角色鉴权用装饰器分层

- 选择：Flask 装饰器链：`auth_required`（解析 JWT、注入 `g.current_user`）→ `role_required('teacher'|'student')`（按需）→ 视图函数。班级过滤在视图调用 repository 时强制。
- 理由：分层清晰、可测；学生上传被拒在 `role_required('teacher')` 装饰器直接返回 403，不进入视图。
- 备选：基于类的视图（CBV）+ mixin。未选，因本变更路由简单，装饰器更直接。

### D5：未登录响应区分页面与 API

- 选择：`auth_required` 检测 `Accept: text/html` 或匹配页面路由前缀时返回 302 到 `/login?next=<原路径>`；其余返回 401 JSON。`GET /health` 与 `POST /auth/login` 不挂该装饰器。
- 理由：满足"引导到登录页"同时不破坏 API 客户端契约。

### D6：上传写入与班级归属一致性（上传数据流）

- 选择：`POST /materials` 视图忽略请求体里的 `classId`，新记录 `class_id` 一律取 `g.current_user.classId`；存储键用 `materials/<classId>/<uuid>/<filename>`。
- 选择：上传数据流按以下顺序串联，每步在前序放行后才执行：
  1. 请求到达 `POST /materials` → `auth_required` 解析 JWT 并注入 `g.current_user`（未登录/失效令牌：API 返回 401，页面 302 到 `/login`）。
  2. `role_required('teacher')` 校验 `g.current_user.role`，`student` 直接返回 403 且不进入后续步骤。
  3. Werkzeug 解析 `multipart/form-data`（`request.files`），校验大小上限与 MIME 白名单，超限/非法类型返回 4xx 且不落盘。
  4. 文件落盘到本地卷 `uploads/materials/<classId>/<uuid>/<filename>`，`<classId>` 取自令牌、`<uuid>` 服务端生成。
  5. `MaterialsRepository.create(class_id=g.current_user.classId, uploader_user_id=g.current_user.userId, filename=..., storage_key=..., mime=..., size=...)` 写入记录，`class_id` 取令牌值，忽略请求体中任何 `classId`。
  6. 返回 201 与新材料记录（含服务端生成的 `id` 与令牌班级的 `classId`）。
- 理由：与 knowledge-materials spec 的"不接受客户端声明班级"直接对应，杜绝越权写入他班；分层使鉴权/限流/落盘/入库职责清晰可测。

### D7：运行时与部署

- 选择：`docker-compose.yml` 仅含 `app` 一个服务（SQLite 为文件数据库，无需独立 db 进程），挂卷持久化 SQLite 文件与 `uploads/`；`.env`/`.env.example` 提供 `JWT_SECRET`、`DATABASE_PATH`、`PORT` 等；app 启动前执行迁移与种子（首次）。`GET /health` 检查 DB 连通性，连通 200 `{"status":"ok"}`，不通 503。
- 选择：启动时校验必需环境变量（`JWT_SECRET`、`DATABASE_PATH`）存在且非空，缺失则立即退出并打印明确错误。
- 理由：满足 app-runtime spec 的"缺失必需环境变量拒绝启动"与"一键启动后服务可用"。

## Risks / Trade-offs

- [JWT 不可主动失效] → 折中接受短 `exp`；后续可加黑名单（非本变更范围）。
- [应用层过滤是唯一隔离权威] → 用强约束的 repository API（禁止裸 `find_by_id`）+ 集成测试覆盖跨班拒绝场景；后续若迁到 PostgreSQL 可叠加 RLS 作纵深防御。
- [初始账号依赖种子脚本] → 明确种子仅用于本地/演示，生产部署需另行提供账号初始化流程（非本变更范围）。
- [文件存储本地卷] → 本变更用本地挂载卷足够；未来切对象存储需改 `storage_key` 解析层，spec 不绑死存储后端。
- [前端极简] → 仅做登录页与受保护页面示意以验证跳转，不构成完整前端工程；后续可替换为独立前端项目。

## Migration Plan

1. 提供迁移脚本建 `classes`、`users`、`materials` 三表与必要索引（`users.class_id`、`materials.class_id`）。
2. 提供种子脚本预置若干班级、教师、学生账号（密码 bcrypt 哈希）。
3. `docker compose up` 首次启动时 app 自动执行迁移与种子，随后监听端口并响应 `GET /health`。
4. 回滚：删除容器与卷即可回到空状态；无既有数据迁移风险（greenfield）。

## Open Questions

- 文件上传大小上限与允许的 MIME 白名单：本变更暂定限制（如 ≤50MB、文档/图片常见类型），具体阈值可在实现阶段定，不改变 spec 行为（拒绝超限与非法类型即可）。
