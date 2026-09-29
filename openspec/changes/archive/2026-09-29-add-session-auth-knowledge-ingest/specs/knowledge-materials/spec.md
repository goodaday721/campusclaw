## MODIFIED Requirements

### Requirement: 教师上传材料写入知识库

系统 SHALL 提供 `POST /materials` 接口供教师上传教学材料；仅接受扩展名为 `.txt` 或 `.md` 的文件并强制大小上限，其余一律拒绝且不落盘不写库；存储文件名 MUST 由服务端生成，MUST NOT 使用客户端原始文件名作为存储路径；上传落盘成功后 MUST 在同一事务中向 materials 表与 knowledge_entries 表各写入一条记录（后者保存材料正文），两记录的 `classId` 均为该教师所属班级；事务任一步失败 MUST 回滚两表并清理已写入的文件，MUST NOT 产生孤儿文件或孤儿记录；成功返回 201。

#### Scenario: 教师上传成功
- **WHEN** 已登录的教师携带有效会话调用 `POST /materials` 并提交 `.txt` 或 `.md` 文件
- **THEN** 系统返回 201，materials 表新增 `classId` 等于该教师所属班级的记录，knowledge_entries 表同时新增指向该材料且含正文的记录，两记录班级一致

#### Scenario: 上传材料记录归属班级
- **WHEN** 教师上传成功
- **THEN** 新增记录的 `classId` 来自服务端会话解析的用户班级，不接受请求体中由客户端声明的 `classId`

#### Scenario: 白名单外类型被拒绝
- **WHEN** 教师提交 `.pdf`、`.docx`、图片等白名单外扩展名的文件
- **THEN** 系统返回 4xx，磁盘不产生文件，materials 与 knowledge_entries 表均无记录

#### Scenario: 事务失败无残留
- **WHEN** 上传过程中数据库写入失败（如正文插入失败）
- **THEN** 两表整体回滚，已写入的文件被清理，最终状态为"无文件、无记录"

#### Scenario: 超过大小上限被拒绝
- **WHEN** 教师提交超过配置大小上限的 `.txt`/`.md` 文件
- **THEN** 系统返回 4xx，不落盘、不写库

### Requirement: 本班材料列表可查

系统 SHALL 提供 `GET /materials` 接口返回当前用户本班材料列表；返回结果 MUST 经服务端按当前用户会话解析的 `classId` 过滤，且学生与教师均可读取本班列表。

#### Scenario: 学生查询本班材料列表
- **WHEN** 已登录的学生携带有效会话调用 `GET /materials`
- **THEN** 系统返回 200 与本班材料记录数组，不含任何非本班记录

#### Scenario: 教师刚上传的材料出现在本班列表
- **WHEN** 教师上传材料成功后，本班任意成员调用 `GET /materials`
- **THEN** 返回列表中包含刚上传的这条记录

### Requirement: 上传写入与班级隔离协同

材料与知识库正文写入 MUST 使用服务端会话解析的 `classId` 作为新记录归属，两表使用同一班级值；读取 MUST 复用班级隔离的服务端过滤，确保写入与读取的班级边界一致。

#### Scenario: 客户端声明的班级被忽略
- **WHEN** 教师上传请求体中包含与会话班级不同的 `classId`
- **THEN** 系统以会话解析的 `classId` 写入两表记录，并返回 201；请求体中的 `classId` 不影响归属

## ADDED Requirements

### Requirement: 本班材料可下载

系统 SHALL 提供材料下载能力，教师与学生均可下载本班材料并取回文件内容；跨班材料与不存在的材料 MUST 返回同构 404；下载 MUST NOT 泄露其他班级的材料。

#### Scenario: 本班学生下载材料成功
- **WHEN** 已登录的学生请求下载本班材料
- **THEN** 系统返回文件内容，内容与上传时保存的正文一致

#### Scenario: 跨班下载与不存在同构 404
- **WHEN** 用户请求下载非本班材料或不存在的材料
- **THEN** 系统返回相同结构的 404 响应，二者不可区分
