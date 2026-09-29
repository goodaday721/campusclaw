## MODIFIED Requirements

### Requirement: Docker Compose 启动

系统 MUST 提供一份 `docker-compose.yml`，编排 `web`、`api`、`db`、`qdrant` 四个服务：`web` 为 Nginx 反向代理并唯一映射宿主机端口（默认 `8080:80`），`api` 为 Flask 应用且不映射宿主机端口，`db` 为 MySQL 8.0 且不映射宿主机端口，`qdrant` 为向量库且不映射宿主机端口；执行 `docker compose up` 后四服务一同启动，api 自动完成迁移、种子初始化并对种子材料按 auto 策略补齐检索索引（切片立即写入；嵌入经服务端网关尽力完成，失败的切片标记 failed 但不阻断启动），无需手动初始化即可经 web 入口响应 `GET /health`。api 启动 MUST NOT 因 Qdrant 或模型网关暂不可用而阻塞退出——关键字检索不依赖二者，须在启动后立即可用。

#### Scenario: 一键启动后服务可用

- **WHEN** 在仅装有 Docker 的干净环境中执行 `docker compose up --build -d`
- **THEN** web、api、db、qdrant 四容器启动，MySQL 完成初始化，api 自动执行迁移、种子与种子材料切片，宿主机访问 `http://localhost:8080/health` 返回 200，且此时关键字检索立即可用

#### Scenario: 标准启动流程可复现

- **WHEN** 使用者按 README 执行 `cp .env.example .env`（填写必填项）、`docker compose up --build -d`、`docker compose ps`
- **THEN** 四服务均为运行状态，无需任何本机语言环境或额外配置即可使用整套服务

### Requirement: 网络暴露控制

Compose 编排中 MUST 仅 `web` 服务配置宿主机端口映射（默认 `8080:80`）；`api`、`db` 与 `qdrant` 服务 MUST NOT 映射任何宿主机端口，仅通过 Compose 内部网络互通；宿主机对 api/db/qdrant 的直连 MUST 被拒绝。模型嵌入与对话网关 MUST 仅由 api 服务端调用，浏览器 MUST NOT 直连向量库或模型网关。

#### Scenario: 仅 web 对宿主机可达

- **WHEN** 在宿主机分别访问 web 的映射端口、api 的内部端口、db 的 3306 端口与 qdrant 的内部端口
- **THEN** 仅 web 的映射端口可访问，api、db 与 qdrant 因无端口映射而无法直连

#### Scenario: web 反向代理转发到 api

- **WHEN** 宿主机浏览器访问 `http://localhost:8080` 下的任意业务路径
- **THEN** 请求经 Nginx 转发到内部网络的 api 服务并得到正常响应

### Requirement: 敏感配置只来自服务端环境变量

会话时效、数据库连接配置、数据库凭据、Qdrant 连接配置以及嵌入/对话模型网关的地址、密钥与模型名等敏感配置 MUST 仅来自服务端环境变量，并提供 `.env.example` 模板标注全部必填项与可选项默认值；MUST NOT 硬编码在源码、提交真实密钥进版本库或出现在客户端可访问的资源中。缺少数据库或会话等启动必需环境变量时服务 MUST 拒绝启动；模型网关凭据缺失或网关不可用时，依赖该网关的检索/问答模式 MUST 明确返回 503，关键字检索等不依赖网关的功能保持可用，MUST NOT 将密钥或网关原始错误细节下发浏览器。

#### Scenario: 缺失必需环境变量时拒绝启动

- **WHEN** 服务启动时缺少数据库连接配置或会话时效等必需环境变量
- **THEN** 服务进程退出并记录明确的错误，不监听端口、不提供任何业务接口

#### Scenario: 模板不含真实密钥

- **WHEN** 查看 `.env.example` 与版本库内容
- **THEN** 模板仅含占位值与填写说明，真实密码与网关密钥仅存在于本地 `.env`

#### Scenario: 网关未配置时功能降级

- **WHEN** 嵌入或对话网关凭据未配置（或网关不可达）时用户发起向量检索或问答
- **THEN** 系统返回 503 与不含密钥的明确错误信息，且同一时刻关键字检索仍正常返回 200
