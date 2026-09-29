## MODIFIED Requirements

### Requirement: 预置演示数据

系统 SHALL 在首次启动时通过迁移与种子脚本预置最小可用的演示数据，至少包含两个班级、分属不同班级的教师与学生账号，以及分属两个班级、标题可明确区分的示例材料（含知识库正文记录）；种子脚本中所有密码 MUST 以单向哈希（bcrypt 或 argon2）存储；重复启动 MUST NOT 产生重复预置记录。

#### Scenario: 首次启动预置演示数据
- **WHEN** 执行 `docker compose up` 且数据库为空
- **THEN** 迁移与种子自动执行，数据库中出现至少两个班级、两名教师（分属 A/B 班）、两名学生（分属 A/B 班）与两份标题可区分的班级材料（含正文），可用预置账号登录

#### Scenario: 种子密码均为哈希
- **WHEN** 种子脚本执行完毕后查询用户表
- **THEN** 所有预置账号的密码字段为 bcrypt/argon2 哈希值，表中不存在明文密码

#### Scenario: 重复启动不重复预置
- **WHEN** 在已有预置数据的数据库上再次执行 `docker compose up`
- **THEN** 种子脚本不重复插入相同账号、班级与材料，已有记录数量与内容保持不变

### Requirement: 敏感配置只来自服务端环境变量

会话时效、数据库路径等敏感配置 MUST 仅来自服务端环境变量；MUST NOT 硬编码在源码、提交进版本库或出现在客户端可访问的资源中。

#### Scenario: 缺失必需环境变量时拒绝启动
- **WHEN** 服务启动时缺少数据库路径或会话时效等必需环境变量
- **THEN** 服务进程退出并记录明确的错误，不监听端口、不提供任何业务接口

## ADDED Requirements

### Requirement: Compose 重启数据持久

数据库文件与上传目录 MUST 存放于 Docker 数据卷中；执行 `docker compose down` 后再 `docker compose up`（不带 `-v`）MUST 保留全部账号、会话与材料数据；仅 `down -v` 才允许清空数据。

#### Scenario: down 后 up 数据仍在
- **WHEN** 上传材料并确认可查后，执行 `docker compose down` 再执行 `docker compose up`
- **THEN** 使用原账号仍可登录，已上传的材料仍在列表中且可下载

#### Scenario: down -v 主动重置
- **WHEN** 执行 `docker compose down -v` 后再 `docker compose up`
- **THEN** 数据卷被清空，数据库重新执行迁移与种子预置
