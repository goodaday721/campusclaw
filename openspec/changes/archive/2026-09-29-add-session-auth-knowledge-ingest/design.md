## Context

上一变更 add-auth-class-isolation（已归档）交付了 JWT 认证 + 三张表 + 单写 materials 的上传。第 3 课课件给出硬性要求：服务端会话（明确不采用 JWT）、五张表（sessions、knowledge_entries 缺失）、`.txt`/`.md` 白名单、materials + knowledge_entries 同事务入库、本班可下载、Compose 数据卷持久。本变更在不更换技术栈（Flask + SQLite + 单容器 Compose）的前提下对齐课件行为契约。

## Goals / Non-Goals

**Goals**

- 认证切换为服务端会话：sessions 表 + HttpOnly Cookie，登录换发新会话标识，登出即删行，每请求查库取角色/班级
- 数据模型扩为五张表，两张业务表带非空 + 索引的 `class_id` 租户列
- 上传：`.txt`/`.md` 白名单 + 大小上限，服务端生成存储名，两表同事务，失败回滚并清理文件
- 本班材料下载；跨班与不存在同构 404
- Compose down→up 数据持久可验收

**Non-Goals**

- 正文切分、向量嵌入与检索问答（第 4 课）
- 对话助手、作业提交与批改（第 5/7 课）
- CSRF Token 表单字段（本课以同源 + SameSite=Lax 缓解，课件只要求防会话固定与失效语义）
- Nginx 反向代理层与多服务拆分（课件原型为 web/api/db 三服务，本仓库保持 Flask 单服务等价栈，行为契约不变）
- 注册、找回密码、平台级超管

## Decisions

### D0：会话标识与存储

- 会话标识：`secrets.token_urlsafe(32)` 不透明随机串，存 `sessions` 表（id 主键、user_id 外键、expires_at），无签名密钥
- Cookie：HttpOnly、SameSite=Lax、Path=/，名字 `session_id`；Secure 属性留待生产 HTTPS（演示环境 HTTP 不设，避免 Cookie 被浏览器丢弃）
- 登录：校验通过后删除浏览器带来的旧会话行 → 插入新行 → Set-Cookie 新标识（会话固定防御）
- 登出：`POST /auth/logout` 删行 + 清 Cookie；未登录调用返回 204 不报错
- 每请求：`auth_required` 读 Cookie → 查 sessions（expires_at > now）→ JOIN users 取 role/classId 存 `g.current_user`；过期/缺失 → 401（API）/302（页面）

### D1：五张表与租户列（迁移 002）

- `sessions(id TEXT PK, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at TEXT NOT NULL)` + user_id 索引
- `knowledge_entries(id INTEGER PK, material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE, class_id INTEGER NOT NULL REFERENCES classes(id), content TEXT NOT NULL, source TEXT NOT NULL)` + material_id、class_id 索引
- `materials` 已有 class_id 非空 + 索引，无需改动
- 迁移保持 `001` 不动，新增 `002_sessions_knowledge.sql` 幂等执行

### D2：上传事务与失败清理

- 顺序：角色校验（403，未落盘）→ 白名单（`.txt`/`.md`，4xx）→ 大小上限（4xx）→ 生成存储名 `<uuid>.<ext>` 落盘 `uploads/materials/<classId>/` → 读取正文 → 单事务插 materials + knowledge_entries → 201
- 任一 DB 步失败：`conn.rollback()` 两表 + `os.remove` 已落盘文件 → 500，无孤儿
- `source` 字段记录原始文件名（仅作展示来源，不作存储路径）

### D3：下载

- `GET /materials/<id>/download`：教师与学生同权，`find_by_id_scoped_to_class(classId, id)` 命中则 `send_file`（`as_attachment=True`，下载名用 source），未命中返回与详情一致的同构 404

### D4：配置

- 移除 `JWT_SECRET`；新增 `SESSION_TTL_HOURS`（必需）与 `SESSION_COOKIE_NAME`（默认 `session_id`）
- `.env.example`、config.py、run.py 启动校验同步更新；`requirements.txt` 移除 PyJWT

### D5：种子数据

- 保留两班师生；每班补一条标题可区分的示例材料（如"A 班·第 3 课阅读材料"/"B 班·第 3 课阅读材料"）及对应 knowledge_entries 正文，`INSERT OR IGNORE` 幂等

### D6：测试与 E2E

- pytest 全量从 Bearer 头改为 Cookie 会话；新增：换发标识、登出失效、白名单拒绝、事务失败清理、下载同构 404
- e2e_test.py 改用 `requests.Session()` 走 Cookie 流程，断言两表记录与 down→up 持久（本机验证时若 Docker 可用）

## Risks / Trade-offs

- SameSite=Lax 不防同站 CSRF，课件未要求 CSRF Token，本课接受此风险并记录
- SQLite 单写者：事务内两表插入为同步短事务，冲突概率低；若正文读取失败须在落盘后尽快失败以缩小窗口
- 旧 JWT 凭证直接失效（BREAKING），演示前须重新登录
- 迁移 002 对已存在的旧库需可重复执行；演示环境通常重建数据卷，风险低

## Migration Plan

1. 合入迁移 002 + 会话认证（旧 JWT 路由同时移除）
2. 上传链路切服务层事务 + 白名单收紧
3. 种子与测试适配，全量回归
4. Compose 重建镜像，down→up 验证持久

## Open Questions

（无）
