## Context

当前实现（见已归档变更 add-session-auth-knowledge-ingest）：Flask + SQLite 单容器，`docker-compose.yml` 仅一个 `app` 服务映射 5000 端口；`app/db/connection.py` 封装 sqlite3 连接与 `executescript` 迁移；五张表（classes/users/sessions/materials/knowledge_entries）由 `migrations/001、002` 建立且全 `IF NOT EXISTS`；会话存 `sessions` 表（非进程内存）；上传在服务层单事务写 materials + knowledge_entries；`GET /health` 现含 DB 探活（失败 503）；测试经 conftest 的 `test_db` fixture 建临时 SQLite 库。数据库为嵌入式文件，无独立进程。

## Goals / Non-Goals

**Goals:**

- Compose 三服务：`web`(Nginx 反代，唯一宿主机端口 8080) / `api`(Flask，仅内网) / `db`(MySQL 8.0，仅内网 + named volume)。
- api 启动自带 MySQL 就绪重试；`/health` 只做存活判定，不含 DB 探活。
- 数据层整体迁移到 MySQL：迁移 SQL、连接层、仓库层、种子、上传事务、测试设施。
- README 从零复现流程 + `.env.example` 模板 + 单实例声明。

**Non-Goals:**

- 不做 MySQL 主从/高可用、多副本横向扩展（单实例声明）。
- 不做 HTTPS/TLS、生产级 Nginx 调优、CDN/静态资源加速。
- 不搬迁 SQLite 历史数据（`down -v` 重建即可）。
- 不引入 ORM/连接池框架（保持现有薄仓库层风格）。

## Decisions

### D1 三服务拓扑与端口

```yaml
web:  nginx:alpine + 挂载 nginx.conf；ports: "${WEB_PORT:-8080}:80"
api:  build .；不配置 ports；env_file .env；volumes: ./uploads:/app/uploads
db:   mysql:8.0；不配置 ports；named volume mysql_data:/var/lib/mysql；
      启动参数 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
```

- 端口收敛到 web 是课件验收项（最小攻击面）；api 监听 5000 仅 `expose` 级别（Compose 内部可见）。
- 备选"db 临时映射 3306 便于本机测试"被拒：违反"仅 web 映射宿主机端口"的硬性验收，测试改走容器内执行（见 D8）。
- Nginx 仅做反代，不直接 serve uploads 静态文件——静态直出会绕过 api 的班级隔离鉴权；下载必须经 api 流式返回。

### D2 MySQL 驱动与连接层

选 **PyMySQL**（纯 Python，零系统依赖，镜像构建简单；`mysql-connector-python` 亦可但无增益；SQLAlchemy/ORM 超出 Non-Goals）。

- `get_connection()` 重写为 `pymysql.connect(host, port, user, password, database, charset="utf8mb4", cursorclass=DictCursor, autocommit=False)`；`DictCursor` 保持现有 `row["col"]` 访问习惯与 sqlite3.Row 等价。
- 保持**每请求新建连接**的现有模式：天然规避 wait_timeout 8 小时断连与连接池复杂度。
- `executescript()` 是 sqlite3 专属 → 迁移执行改为按 `;` 逐语句拆分后逐条 `execute`（pymysql 单语句执行；不启用 MULTI_STATEMENTS client flag，保持错误定位清晰）。
- 事务模式不变：`autocommit=False` 下由调用方 `commit()/rollback()`，与上传服务现有"服务层控事务"设计完全兼容。

### D3 迁移 SQL 方言重写（001/002）

- `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGINT AUTO_INCREMENT PRIMARY KEY`。
- `TEXT` → 按列定长 `VARCHAR(255)`（filename、source、mime、name、role、username）或 `TEXT`（password_hash、content）；MySQL TEXT 不能带默认值。
- `role` 约束改 `ENUM('teacher','student')`（MySQL 8.0 原生；备选 CHECK 8.0.16+ 虽支持但 ENUM 更常规）。
- `created_at TEXT DEFAULT (datetime('now'))` → `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP`；`expires_at` → `DATETIME NOT NULL`；绑定参数统一传 UTC `datetime` 对象。
- **幂等策略**：MySQL 无 `CREATE INDEX IF NOT EXISTS` → 索引全部内联为 `CREATE TABLE` 内的 `KEY idx_xxx (col)` 定义，配 `CREATE TABLE IF NOT EXISTS` 即可整体幂等。
- `INSERT OR IGNORE` → `INSERT IGNORE`（种子幂等语义不变）。

### D4 配置面：分立 DB 变量替代 DATABASE_URL

新增 `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`（必填：DB_PASSWORD 等凭据项），移除 `DATABASE_PATH`；api 服务与 db 服务共享同一组变量（db 侧映射为 `MYSQL_DATABASE/MYSQL_USER/MYSQL_PASSWORD/MYSQL_ROOT_PASSWORD`）。

- 选分立变量而非单一 `DATABASE_URL`：与 `mysql:8.0` 镜像的环境变量契约对齐，同一份 `.env` 同时喂两个服务，避免 URL 解析与两处凭据定义。
- 新增 `UPLOAD_ROOT`（容器内默认 `/app/uploads`）：storage_key 的相对基准从"SQLite 文件父目录"改为显式 `UPLOAD_ROOT`；上传服务、下载路由（`send_file` 绝对路径解析）、种子写文件三处同步改。`data/` 目录与 `./data:/app/data` 挂载随之移除。
- `run.py` 启动校验同步：缺 DB_PASSWORD 等必需变量时退出非 0 并给明确错误。

### D5 就绪重试与初始化时机

- `app/__init__.py` 的 `_init_db`（迁移 + 种子）外包一层重试：最多 30 次 × 2s（共 60s），仅对 pymysql 连接类 `OperationalError` 重试；重试超限抛异常使 api 进程退出，由 `restart: unless-stopped` 兜底重启。
- `create_app` 现有的 `try/except pass`（为 /health 降级服务）随 /health 去 DB 化一并移除，改为 fail-fast——初始化失败即退出，避免"启动了但永远 5xx"的假活。
- 明确 `depends_on` 仍保留（启动顺序提示），但就绪保证只依赖 api 自身重试（课件要求点）。

### D6 /health 简化

移除 `SELECT 1` 探活，恒返回 `200 {"status":"ok"}`；数据库故障由业务请求 5xx 与 api 日志体现。此为课件"健康检查分离"的显式行为变化（对应 delta MODIFIED），非实现细节。

### D7 Nginx 配置

新增 `deploy/nginx.conf`：`listen 80`；`location / { proxy_pass http://api:5000; }` 附 `Host/X-Real-IP/X-Forwarded-For/X-Forwarded-Proto` 头；`client_max_body_size 50m`（与 UPLOAD_MAX_SIZE_MB 上限一致，避免大文件被 Nginx 先拒 413 造成行为不一致）。

### D8 测试设施（pytest / e2e）

- conftest `test_db` fixture 改为：连接 `TEST_DB_*` 环境变量指向的 MySQL 实例 → `DROP DATABASE`/`CREATE DATABASE` 测试库（如 `campusclaw_test`）→ 顺序执行 001/002 迁移 + 种子；各测试同现状使用。
- **标准测试路径**：`docker compose exec api pytest`（容器内直连 db 服务，不依赖任何宿主机端口）。本机开发可选自备 MySQL 或 `docker run --rm -p 3307:3306 mysql:8.0` 并用 `TEST_DB_*` 覆盖。
- `e2e_test.py`：test-client 模式改连测试库；HTTP 模式 base_url 改 `http://localhost:8080`（走 web 入口）。
- 兼容注意：SQLite 与 MySQL 行为差异点——`lastrowid`（pymysql 同名可用）、布尔返回（无布尔列，不受影响）、时间比较（统一 datetime 对象绑定）。

### D9 种子固定 id 幂等

沿用"显式 id + INSERT IGNORE + 文件 exists 跳过"策略；MySQL 下显式 id 插入会推进 AUTO_INCREMENT，属预期行为（幂等性看记录数不重复，非 id 复用）。种子文件写入路径改用 `UPLOAD_ROOT`。

## Risks / Trade-offs

- [MySQL 首次初始化慢（建库+字符集）导致 api 先起] → api 60s 重试窗口覆盖；`restart: unless-stopped` 兜底。
- [wait_timeout 长连接失效] → 保持每请求建连模式，天然规避。
- [/health 不再反映 DB 故障] → 有意的课件要求；DB 故障经业务 5xx 与日志暴露，避免 DB 抖动引发健康检查误杀。
- [SQLite→MySQL 行为差异漏测（严格模式、长度、时区）] → 迁移 SQL 显式长度/utf8mb4/UTC datetime 绑定；测试库即 MySQL，全量 pytest 覆盖。
- [db 不暴露端口造成本机调试不便] → 标准路径 `docker compose exec api pytest`；需要 GUI 时用户自行临时 `docker run` 映射，不影响交付形态。
- [旧 SQLite data/ 目录残留误导] → README 说明数据现位于 MySQL volume；`down -v` 语义不变。
- [Windows bind mount 上传目录性能] → 单机课程演示量级可接受，不做卷优化。

## Migration Plan

1. 合并后执行 `docker compose down`（旧单容器停止），删除旧 `./data` 遗留（不搬迁数据）。
2. `cp .env.example .env` 填写 DB 密码等 → `docker compose up --build -d`，api 重试连接并自动迁移+种子。
3. 验证：`docker compose ps` 三服务 Up；`http://localhost:8080/health` 200；预置账号登录、上传、下载、跨班 404；`down`→`up` 数据保留。
4. 回滚：`git revert` 回单容器 SQLite 版本（旧数据不兼容，视为重置）。

## Open Questions

（无——测试库访问方式已在 D8 给出标准路径，配置形态已在 D4 定案。）
