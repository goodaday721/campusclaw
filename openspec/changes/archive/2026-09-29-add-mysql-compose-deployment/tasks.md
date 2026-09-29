## 1. 配置与依赖

- [x] 1.1 `requirements.txt` 新增 PyMySQL，确认 `pip install -r requirements.txt` 在干净环境下成功；verify: `python -c "import pymysql"` 可用且版本打印正常
- [x] 1.2 `app/config.py` 移除 `DATABASE_PATH`，新增 `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`（凭据类必需）与 `UPLOAD_ROOT`（默认 `/app/uploads`）；`run.py` 启动校验同步；新建 `.env.example`（占位值 + 每项用途注释，含 `WEB_PORT`），`.env` 更新为本地实际值；verify: 缺 `DB_PASSWORD` 时 `python run.py` 退出码非 0 且错误信息明确；`.env.example` 中无真实密钥

## 2. 数据层迁移到 MySQL

- [x] 2.1 重写 `migrations/001_initial_schema.sql` 为 MySQL 方言：`AUTO_INCREMENT` 主键、`VARCHAR(n)`/`TEXT` 列型、`role ENUM('teacher','student')`、`created_at DATETIME DEFAULT CURRENT_TIMESTAMP`、索引内联为表内 `KEY` 定义；verify: 对空 MySQL 测试库连续执行两次迁移无报错、无重复对象
- [x] 2.2 重写 `migrations/002_sessions_knowledge.sql`：`sessions.expires_at DATETIME`、`knowledge_entries` 同方言、索引内联；verify: 同 2.1，五张表结构与索引齐全
- [x] 2.3 重写 `app/db/connection.py`：`pymysql.connect`（DictCursor、`autocommit=False`、`utf8mb4`）+ `run_migration` 按 `;` 拆分逐条执行；verify: pytest——迁移可重复执行且幂等，连接可执行参数化查询
- [x] 2.4 仓库层适配（users/sessions/materials/knowledge）：占位符 `?`→`%s`、时间统一 UTC `datetime` 对象绑定、`INSERT OR IGNORE`→`INSERT IGNORE`，`lastrowid` 与"服务层控事务"模式保持；verify: pytest 全部 CRUD 用例通过
- [x] 2.5 `seeds/seed.py` 适配：参数化写法与时间类型、种子文件写入基准改 `UPLOAD_ROOT`；verify: 种子连续执行两次后 classes/users/materials/knowledge_entries 计数不变且两班材料标题可区分

## 3. 应用层适配

- [x] 3.1 `app/__init__.py`：`_init_db`（迁移+种子）外包数据库就绪重试（最多 30 次 × 2s，仅对 pymysql 连接类 `OperationalError` 重试，超限抛错退出），移除 `create_app` 中 `try/except pass` 改 fail-fast；verify: pytest——db 不可达时初始化按预期重试并最终失败退出，db 就绪时一次通过
- [x] 3.2 `app/routes/health.py` 移除 DB 探活，恒返回 `200 {"status":"ok"}`；verify: pytest——`/health` 200 且 monkeypatch `get_connection` 抛异常时仍 200（存活判定不受 DB 影响）
- [x] 3.3 `app/services/upload.py` 与 `app/routes/materials.py`：落盘/下载路径基准改 `UPLOAD_ROOT`（`send_file` 用 `.resolve()` 绝对路径）；verify: pytest——上传 201 两表一致、本班下载内容一致、跨班/不存在同构 404

## 4. 测试设施

- [x] 4.1 `tests/conftest.py`：`TEST_DB_*` 环境变量连接 MySQL，`test_db` fixture 改为 drop/create 测试库 + 顺序执行 001/002 迁移与种子；verify: `pytest` 全量通过（标准路径 `docker compose exec api pytest`）
- [x] 4.2 `e2e_test.py`：test-client 模式连测试库；HTTP 模式 `base_url` 改 `http://localhost:8080`（经 web 入口）；verify: 两种模式全部检查项通过

## 5. Compose 三服务编排

- [x] 5.1 新增 `deploy/nginx.conf`：`listen 80`、`proxy_pass http://api:5000`、`Host/X-Real-IP/X-Forwarded-For/X-Forwarded-Proto` 透传、`client_max_body_size 50m`；verify: compose up 后宿主机经 `http://localhost:8080/health` 得 200
- [x] 5.2 重写 `docker-compose.yml`：`web`（nginx:alpine，唯一 `ports: "${WEB_PORT:-8080}:80"`，挂载 nginx.conf）、`api`（build .，无 ports，env_file，`./uploads:/app/uploads` 挂载，`restart: unless-stopped`）、`db`（mysql:8.0，无 ports，named volume `mysql_data:/var/lib/mysql`，utf8mb4 启动参数，凭据来自共享 env），`api depends_on db`；verify: `docker compose config` 无告警，`up -d` 后 `docker compose ps` 三服务 Up，宿主机直连 5000/3306 均拒绝
- [x] 5.3 确认 `Dockerfile` 无需系统级 MySQL 客户端依赖（PyMySQL 纯 Python）并完成构建；verify: `docker compose build` 成功且镜像内 `python -c "import pymysql"` 正常

## 6. 文档与端到端验收

- [x] 6.1 `README.md` 补部署章节：标准流程（`cp .env.example .env` → 填写 → `docker compose up --build -d` → `docker compose ps` → `http://localhost:8080`）、预置账号表（两班师生）、健康检查地址、数据持久说明（`down` 保数据、`down -v` 重置）、**单实例部署声明**及多副本限制；verify: 按 README 在干净环境从零执行可完整跑通
- [x] 6.2 持久化与暴露验收：上传材料 → `docker compose down` → `up`（不带 `-v`）→ 原账号可登录、已传材料可查可下载、MySQL 数据在 named volume 中；verify: e2e HTTP 模式全过 + 直查 MySQL 记录数重启前后一致
- [x] 6.3 全量场景回归并保留输出记录；verify: `openspec validate add-mysql-compose-deployment --strict` 通过，且 pytest + e2e 场景逐条执行留痕
