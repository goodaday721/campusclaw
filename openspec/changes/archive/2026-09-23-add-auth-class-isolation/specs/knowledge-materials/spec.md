## Purpose

让教师把教学材料上传并写入知识库，本班学生与教师可在本班材料列表中查到这条记录，并与班级隔离能力协同确保不跨班可见。

## ADDED Requirements

### Requirement: 教师上传材料写入知识库

系统 SHALL 提供 `POST /materials` 接口供教师上传教学材料；上传成功后 MUST 在知识库材料表中创建一条记录，记录 MUST 包含所属 `classId`、上传教师 `userId`、文件位置与元数据。

#### Scenario: 教师上传成功
- **WHEN** 已登录的教师携带有效 JWT 调用 `POST /materials` 并提交合法文件
- **THEN** 系统返回 201 与新材料记录，且知识库材料表新增一条 `classId` 等于该教师所属班级的记录

#### Scenario: 上传材料记录归属班级
- **WHEN** 教师上传成功
- **THEN** 新增记录的 `classId` 来自服务端解析的令牌班级，不接受请求体中由客户端声明的 `classId`

### Requirement: 本班材料列表可查

系统 SHALL 提供 `GET /materials` 接口返回当前用户本班材料列表；返回结果 MUST 经服务端按当前用户 `classId` 过滤，且学生与教师均可读取本班列表。

#### Scenario: 学生查询本班材料列表
- **WHEN** 已登录的学生携带有效 JWT 调用 `GET /materials`
- **THEN** 系统返回 200 与本班材料记录数组，不含任何非本班记录

#### Scenario: 教师刚上传的材料出现在本班列表
- **WHEN** 教师上传材料成功后，本班任意成员调用 `GET /materials`
- **THEN** 返回列表中包含刚上传的这条记录

### Requirement: 上传写入与班级隔离协同

材料写入 MUST 使用服务端令牌中的 `classId` 作为新记录归属；读取 MUST 复用班级隔离的服务端过滤，确保写入与读取的班级边界一致。

#### Scenario: 客户端声明的班级被忽略
- **WHEN** 教师上传请求体中包含与令牌不同的 `classId`
- **THEN** 系统以令牌中的 `classId` 写入记录，并返回 201；请求体中的 `classId` 不影响归属
