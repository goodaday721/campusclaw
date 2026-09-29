## MODIFIED Requirements

### Requirement: 教师上传材料写入知识库

系统 SHALL 提供 `POST /materials` 接口供教师上传教学材料；仅接受扩展名为 `.txt` 或 `.md` 的文件并强制大小上限，其余一律拒绝且不落盘不写库；存储文件名 MUST 由服务端生成，MUST NOT 使用客户端原始文件名作为存储路径；上传落盘成功后 MUST 在同一事务中向 materials 表与 knowledge_entries 表各写入一条记录（后者保存材料正文），两记录的 `classId` 均为该教师所属班级；事务任一步失败 MUST 回滚两表并清理已写入的文件，MUST NOT 产生孤儿文件或孤儿记录；成功返回 201。材料事务提交成功后，系统 SHALL 继续对该正文执行检索索引步骤（切分写入 knowledge_chunks、嵌入并写入向量库）；索引步骤失败 MUST NOT 回滚或删除已提交的材料文件与两表记录：切片正文仍为 `index_status=ready`（关键字可检索），仅 `embedding_status` 标记为 `failed` 且不写入不完整向量。

#### Scenario: 教师上传成功

- **WHEN** 已登录的教师携带有效会话调用 `POST /materials` 并提交 `.txt` 或 `.md` 文件
- **THEN** 系统返回 201，materials 表新增 `classId` 等于该教师所属班级的记录，knowledge_entries 表同时新增指向该材料且含正文的记录，两记录班级一致；随后该正文被切分为切片并完成嵌入入库，可用于本班检索

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

#### Scenario: 索引失败不影响已提交材料

- **WHEN** 材料文件与两表记录已成功提交，但随后的切分/嵌入/向量写入失败
- **THEN** 上传结果仍为成功，材料可在本班列表、下载与关键字检索中正常使用，受影响切片 embedding_status 为 failed 且向量库无对应数据，可由教师后续按策略重建索引
