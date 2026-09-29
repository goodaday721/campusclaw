## ADDED Requirements

### Requirement: 网络暴露控制

Compose 编排中 MUST 仅 `web` 服务配置宿主机端口映射（默认 `8080:80`）；`api` 与 `db` 服务 MUST NOT 映射任何宿主机端口，仅通过 Compose 内部网络互通；宿主机对 api/db 的直连 MUST 被拒绝。

#### Scenario: 仅 web 对宿主机可达

- **WHEN** 在宿主机分别访问 web 的映射端口、api 的内部端口与 db 的 3306 端口
- **THEN** 仅 web 的映射端口可访问，api 与 db 因无端口映射而无法直连

#### Scenario: web 反向代理转发到 api

- **WHEN** 宿主机浏览器访问 `http://localhost:8080` 下的任意业务路径
- **THEN** 请求经 Nginx 转发到内部网络的 api 服务并得到正常响应

### Requirement: 数据库就绪重试

api 服务启动时 MUST 自带 MySQL 连接重试逻辑：在数据库未就绪时按有限次数或时限反复重试连接，成功后继续执行迁移与种子；重试上限内数据库持续不可用时，api 进程 MUST 以明确错误退出；就绪等待 MUST NOT 仅依赖 `depends_on` 的启动顺序保证。

#### Scenario: 数据库晚于 api 就绪时最终启动成功

- **WHEN** 首次启动时 db 服务初始化耗时较长，api 先于 MySQL 就绪启动
- **THEN** api 在重试窗口内连上数据库，完成迁移与种子并正常对外服务，不因启动时序直接崩溃

#### Scenario: 重试超限明确失败

- **WHEN** 数据库在重试窗口内持续不可用
- **THEN** api 进程退出，日志给出明确的数据库连接失败原因

### Requirement: 单实例部署边界

本迭代 SHALL 仅支持单实例部署；交付文档 MUST 明确声明单实例边界与多副本限制（上传文件存放于单机数据卷、未做多副本间共享），并说明本迭代未针对横向扩展设计。

#### Scenario: 文档声明单实例限制

- **WHEN** 阅读 README 的部署说明
- **THEN** 可见"仅支持单实例部署"及多副本不受支持的明确声明

## MODIFIED Requirements

### Requirement: Docker Compose 启动

系统 MUST 提供一份 `docker-compose.yml`，编排 `web`、`api`、`db` 三个服务：`web` 为 Nginx 反向代理并唯一映射宿主机端口（默认 `8080:80`），`api` 为 Flask 应用且不映射宿主机端口，`db` 为 MySQL 8.0 且不映射宿主机端口；执行 `docker compose up` 后三服务一同启动，api 自动完成迁移与种子初始化，无需手动初始化即可经 web 入口响应 `GET /health`。

#### Scenario: 一键启动后服务可用

- **WHEN** 在仅装有 Docker 的干净环境中执行 `docker compose up --build -d`
- **THEN** web、api、db 三容器启动，MySQL 完成初始化，api 自动执行迁移与种子，宿主机访问 `http://localhost:8080/health` 返回 200

#### Scenario: 标准启动流程可复现

- **WHEN** 使用者按 README 执行 `cp .env.example .env`（填写必填项）、`docker compose up --build -d`、`docker compose ps`
- **THEN** 三服务均为运行状态，无需任何本机语言环境或额外配置即可使用整套服务

### Requirement: 健康检查端点

系统 SHALL 提供 `GET /health` 端点做服务存活判定；该端点 MUST NOT 要求认证，MUST NOT 返回任何敏感信息，且 MUST NOT 包含数据库探活逻辑——数据库可用性由业务请求体现，健康检查不依赖数据库状态。

#### Scenario: 健康检查成功

- **WHEN** 任意客户端不带凭证调用 `GET /health`
- **THEN** 系统返回 200 与简短存活标识（如 `{"status":"ok"}`），不含密钥、用户或材料数据

#### Scenario: 依赖未就绪时降级

- **WHEN** 数据库连接不可用时调用 `GET /health`
- **THEN** 端点仍返回 200 存活状态，不执行降级判定，不因数据库抖动将服务判定为不健康

### Requirement: 敏感配置只来自服务端环境变量

会话时效、数据库连接配置与数据库凭据等敏感配置 MUST 仅来自服务端环境变量，并提供 `.env.example` 模板标注全部必填项；MUST NOT 硬编码在源码、提交真实密钥进版本库或出现在客户端可访问的资源中。

#### Scenario: 缺失必需环境变量时拒绝启动

- **WHEN** 服务启动时缺少数据库连接配置或会话时效等必需环境变量
- **THEN** 服务进程退出并记录明确的错误，不监听端口、不提供任何业务接口

#### Scenario: 模板不含真实密钥

- **WHEN** 查看 `.env.example` 与版本库内容
- **THEN** 模板仅含占位值与填写说明，真实密码仅存在于本地 `.env`
