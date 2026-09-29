## Why

课程第 3 课将 Docker Compose 三服务编排（web / api / db）列为硬性交付标准：当前仓库是单容器 Flask + SQLite（compose 仅一个 `app` 服务并直接映射 5000 端口），不满足"只有 web 暴露宿主机端口、api/db 仅内网、数据库为独立 MySQL 8.0 服务"的验收项；本机直跑不算合格交付形态，任何人都必须能照 README 从零用几条命令复现整套环境。

## What Changes

- **BREAKING** 数据层由 SQLite 迁移到 MySQL 8.0：连接层改用 PyMySQL，迁移脚本按 MySQL 方言重写（`AUTO_INCREMENT`、`ENGINE=InnoDB`），仓库层 SQL 占位符 `?`→`%s`、`INSERT OR IGNORE`→`INSERT IGNORE`、自增主键取值改 `lastrowid`（ pymysql 一致）与显式事务控制。
- **BREAKING** `GET /health` 移除数据库探活，只做服务存活判定，恒返回 200（服务进程存活即健康）；数据库可用性由 api 启动重试与业务请求体现，避免数据库抖动导致服务被判定不健康。
- Docker Compose 重构为三服务：
  - `web`：Nginx 反向代理，唯一映射宿主机端口（默认 `8080:80`）；
  - `api`：Flask 应用，仅在 Compose 内部网络，不映射任何宿主机端口；
  - `db`：`mysql:8.0`，仅在内部网络，不映射 3306，数据存放于 Docker volume。
- api 启动流程自带数据库连接重试（`depends_on` 只保证启动顺序，不保证 MySQL 完成初始化），就绪等待期间重试而非直接崩溃，避免首次启动 502。
- 配置面调整：移除 `DATABASE_PATH`，新增 `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`（与 mysql:8.0 镜像变量契约对齐，api 与 db 共用一组）与 `UPLOAD_ROOT`、`WEB_PORT`；提供 `.env.example` 模板并标注必填项。
- 上传文件目录继续通过 volume 持久化；MySQL 数据独立 named volume；`down` 后 `up`（不带 `-v`）数据保留，仅 `down -v` 清空。
- README 补齐从零复现标准流程（`cp .env.example .env` → `docker compose up --build -d` → `docker compose ps` → 访问 `http://localhost:8080`）、预置账号、健康检查地址，并明确声明本迭代仅支持单实例部署及多副本限制。
- pytest / e2e 测试设施适配 MySQL（独立测试库，跑测试前重建 schema）。

## Capabilities

### New Capabilities

（无——部署拓扑变化由现有 `app-runtime` capability 承载）

### Modified Capabilities

- `app-runtime`：
  - MODIFIED「Docker Compose 启动」：单容器 SQLite 改为 web/api/db 三服务，db 为 MySQL 8.0；
  - MODIFIED「健康检查端点」：移除"数据库不可用返回 503"的降级行为，只做存活判定；
  - MODIFIED「敏感配置只来自服务端环境变量」：数据库路径改为 MySQL 连接串与凭据；
  - ADDED「网络暴露控制」：仅 web 映射宿主机端口，api/db 仅内网；
  - ADDED「数据库就绪重试」：api 自带连接重试，不依赖 `depends_on` 的时序保证；
  - ADDED「单实例部署边界」：文档声明仅支持单实例及多副本限制。

（`user-auth`、`knowledge-materials`、`class-isolation`、`role-access` 的行为契约不变——本次是数据层与部署形态替换，外部可观察行为等价，不产生 delta。）

## Impact

- **Compose/镜像**：`docker-compose.yml` 重写（三服务 + named volume + 内部网络）；新增 Nginx 配置；`Dockerfile` 更新依赖。
- **数据层**：`app/db/connection.py` 重写（PyMySQL 连接、迁移执行、事务）；`migrations/001_initial_schema.sql`、`002_sessions_knowledge.sql` 方言重写；`seeds/seed.py` 适配。
- **应用层**：`app/config.py`（分立 DB 变量 + UPLOAD_ROOT）、`app/__init__.py`（启动重试 + 迁移种子 fail-fast）、`app/routes/health.py`（去 DB 探活）、`app/repositories/*`（占位符与幂等写法）、`app/services/upload.py`（手动 commit/rollback）、上传/下载路径基准改 `UPLOAD_ROOT`。
- **配置与依赖**：`requirements.txt`（+PyMySQL）、`.env`、`.env.example`（新增模板）、`run.py` 启动校验；`data/` 目录与挂载移除，上传根改 `UPLOAD_ROOT`。
- **测试**：`tests/conftest.py` 及各测试文件、`e2e_test.py` 适配 MySQL 测试库。
- **文档**：`README.md` 从零复现流程、预置账号、单实例声明。

## Non-Goals

- 不做 MySQL 高可用（主从/集群）、多副本横向扩展；本迭代仅支持单实例部署。
- 不做 HTTPS/TLS 终结、域名与生产级 Nginx 调优（仅最小反向代理配置）。
- 不做数据迁移工具（SQLite 旧数据不搬迁，`down -v` 重建即可）。
- 不做检索问答、对话助手、作业提交与批改、SSO、CSRF Token 等本学期未排期功能。
