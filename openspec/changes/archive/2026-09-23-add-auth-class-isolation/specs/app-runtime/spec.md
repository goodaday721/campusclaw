## Purpose

为应用提供运行时契约：通过 Docker Compose 启动整套服务、暴露健康检查端点、并将密钥与连接串等敏感配置仅限于服务端环境变量来源。

## ADDED Requirements

### Requirement: Docker Compose 启动

系统 MUST 提供一份 `docker-compose.yml`，使执行 `docker compose up` 后应用及其依赖（如 SQLite 文件数据库）一同启动并可对外提供服务端口；启动后无需手动初始化即可响应 `GET /health`。

#### Scenario: 一键启动后服务可用
- **WHEN** 执行 `docker compose up`
- **THEN** 应用容器启动并初始化 SQLite 文件数据库，应用监听端口并响应 `GET /health` 返回 200

### Requirement: 健康检查端点

系统 SHALL 提供 `GET /health` 端点，返回服务存活状态；该端点 MUST NOT 要求认证，并 MUST NOT 返回任何敏感信息。

#### Scenario: 健康检查成功
- **WHEN** 任意客户端不带凭证调用 `GET /health`
- **THEN** 系统返回 200 与简短存活标识（如 `{"status":"ok"}`），不含密钥、用户或材料数据

#### Scenario: 依赖未就绪时降级
- **WHEN** 数据库连接不可用时调用 `GET /health`
- **THEN** 系统返回 503 或明确的降级状态，指示服务不健康

### Requirement: 预置演示数据

系统 SHALL 在首次启动时通过迁移与种子脚本预置最小可用的演示数据，至少包含两个班级、分属不同班级的教师与学生账号；种子脚本中所有密码 MUST 以单向哈希（bcrypt 或 argon2）存储；重复启动 MUST NOT 产生重复预置记录。

#### Scenario: 首次启动预置演示数据
- **WHEN** 执行 `docker compose up` 且数据库为空
- **THEN** 迁移与种子自动执行，数据库中出现至少两个班级、两名教师（分属 A/B 班）与两名学生（分属 A/B 班），可用预置账号登录

#### Scenario: 种子密码均为哈希
- **WHEN** 种子脚本执行完毕后查询用户表
- **THEN** 所有预置账号的密码字段为 bcrypt/argon2 哈希值，表中不存在明文密码

#### Scenario: 重复启动不重复预置
- **WHEN** 在已有预置数据的数据库上再次执行 `docker compose up`
- **THEN** 种子脚本不重复插入相同账号与班级，已有记录数量与内容保持不变

### Requirement: 敏感配置只来自服务端环境变量

JWT 密钥、数据库连接串等敏感配置 MUST 仅来自服务端环境变量；MUST NOT 硬编码在源码、提交进版本库或出现在客户端可访问的资源中。

#### Scenario: 缺失必需环境变量时拒绝启动
- **WHEN** 服务启动时缺少 JWT 密钥或数据库连接串环境变量
- **THEN** 服务进程退出并记录明确的错误，不监听端口、不提供任何业务接口
