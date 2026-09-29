# knowledge-retrieval Specification

## Purpose
让教师与学生以一句自然语言在本班材料中完成可追溯的知识检索：正文经切分与向量嵌入入库，支持关键字、向量与混合三种检索模式，每条命中都能回溯到具体材料的具体切片与字符位置；问答接口仅在检索到本班依据后才生成带出处标注的简短回答，无依据时明确告知未找到且不调用生成模型。

## Requirements

### Requirement: 正文切分为切片

材料文件与 `knowledge_entries` 正文事务提交之后，系统 SHALL 将该正文按指定策略切分为切片，写入 MySQL `knowledge_chunks` 表；每条切片 MUST 记录切片正文、所属材料/正文/班级标识、切片序号与在（预处理后）文本中的字符区间，并分别记录正文索引状态 `index_status` 与向量嵌入状态 `embedding_status`：切片正文写入成功后 `index_status` 即为 `ready`（可用于关键字检索，与嵌入是否成功无关），`embedding_status` 为 `pending`/`ready`/`failed`。切分 MUST NOT 改写原始文件与 `knowledge_entries.body_text`，切分与正文落库 MUST NOT 调用嵌入服务或写入向量库。未指定策略时 MUST 使用 `auto`；启动时为种子材料补齐索引同样使用 `auto`。

- `auto`：最大约 800 字、重叠约 80 字，优先在空行、换行、句号处断开；请求中另填的长度参数不生效。
- `custom`：最大长度 100 至 2000 字、重叠比例 0% 至 50%，无断点处按最大长度强制截断；可选择预先移除 URL 与邮箱、将连续空白折叠为单个空格（预处理仅作用于待切分文本，偏移量相对于预处理后文本）。
- `hierarchy`：按 `#`、`##`、`###` 层级分章，标题保留在该章切片内；某章过长时再按 auto 窗口规则切分。

#### Scenario: 默认 auto 切分

- **WHEN** 一份正文超过 800 字的材料上传成功且未指定切分策略
- **THEN** 系统按最大约 800 字、约 80 字重叠切出多条切片，相邻切片存在重叠内容，每条切片带有序号与字符区间，原文文件与 body_text 保持上传时原样

#### Scenario: custom 策略参数边界

- **WHEN** 请求以 custom 策略切分且指定的最大长度超出 100–2000 范围，或重叠比例超出 0%–50%
- **THEN** 系统返回 4xx 且不写入任何切片

#### Scenario: hierarchy 按 Markdown 标题分章

- **WHEN** 一份含 `#`/`##`/`###` 标题的 Markdown 材料以 hierarchy 策略切分
- **THEN** 每章的标题保留在对应章节切片内，过长章节再按 auto 窗口规则二次切分

#### Scenario: 预处理不改写原文

- **WHEN** custom 策略请求移除 URL/邮箱并折叠连续空白
- **THEN** 仅切片文本受预处理影响，knowledge_entries.body_text 仍是上传原文，切片字符区间按预处理后文本记录

### Requirement: 向量嵌入与向量存储

每条 `index_status=ready` 的切片 MUST 由服务端调用兼容 OpenAI `/embeddings` 的嵌入模型转换为一条固定维度浮点向量，并写入向量库 collection `campusclaw_chunks`（余弦度量），成功后该切片 `embedding_status` 置为 `ready`；向量主键 MUST 等于对应 `knowledge_chunks.id`，向量库 payload MUST 仅包含 `class_id`、`material_id`、`knowledge_entry_id`、`chunk_id`、`chunk_index`，MUST NOT 保存切片正文。嵌入调用与向量库 MUST 仅由服务端发起，嵌入密钥 MUST NOT 下发浏览器。嵌入失败时材料记录与正文 MUST 保留、切片 `index_status` 仍为 `ready`（关键字检索不受影响），仅 `embedding_status` 标记为 `failed`，MUST NOT 写入不完整的向量数据。

#### Scenario: 切片向量主键与切片一致

- **WHEN** 一份材料的切片全部嵌入成功
- **THEN** Qdrant 中每条向量的主键等于 MySQL knowledge_chunks 中对应切片的 id，payload 含 class_id/material_id/chunk_index 等标识且不含正文文本，向量维度与 collection 定义一致，对应切片 embedding_status 为 ready

#### Scenario: 嵌入失败保留原文且关键字仍可检索

- **WHEN** 某材料的切片嵌入过程中嵌入网关持续失败
- **THEN** 材料文件、materials 与 knowledge_entries 记录仍然存在，对应切片 index_status 仍为 ready、embedding_status 为 failed，Qdrant 中没有该批切片的向量数据，且该材料仍能被关键字检索命中

### Requirement: 关键字检索

系统 SHALL 提供关键字检索：仅查询 MySQL 全文索引（`FULLTEXT ... WITH PARSER ngram`，ngram token 长度为 2），且 MUST 只检索 `index_status=ready` 的切片；关键字路径 MUST NOT 调用嵌入服务，MUST NOT 访问向量库。

#### Scenario: 原文命中关键字

- **WHEN** 已登录用户以 keyword 模式检索，且查询词直接出现在本班某 ready 切片正文中
- **THEN** 系统返回 200，命中切片按全文相关度由高到低排列，结果不含 failed 切片

#### Scenario: 关键字路径不依赖向量库

- **WHEN** Qdrant 不可用时用户以 keyword 模式检索
- **THEN** 检索仍正常返回 200 与结果，全程不调用嵌入服务或 Qdrant

### Requirement: 向量检索

系统 SHALL 提供向量检索：先将问句经嵌入模型转为向量，再在向量库中按会话班级过滤检索，余弦相似度低于 0.35 的候选 MUST 被丢弃；命中后 MUST 以向量主键回 MySQL 取回切片正文。

#### Scenario: 语义改写命中

- **WHEN** 用户以 vector 模式检索，问句用词与原文不同但语义相近，且最高余弦相似度不低于 0.35
- **THEN** 系统返回 200，候选按余弦相似度由高到低排列，正文内容由 MySQL 回表取得

#### Scenario: 低相似度候选被丢弃

- **WHEN** 向量库中所有候选的余弦相似度均低于 0.35
- **THEN** 该路径视为无候选，不以低相关切片凑数

### Requirement: 混合检索与 RRF 融合

系统 SHALL 提供混合检索并将其作为默认模式：同时执行关键字与向量两条路径，两路各自先独立过滤（含班级条件、ready 状态与 0.35 相似度阈值），再按倒数排名融合 RRF（k=60）融合为最终次序；在某一路径缺席（无候选或该路径依赖不可用但另一路径可用）时，缺席路径 MUST NOT 贡献名次分。

#### Scenario: 两路命中同一切片排名更靠前

- **WHEN** keyword 与 vector 两路都命中同一切片
- **THEN** 融合排序后该切片排在仅单路命中的切片之前

#### Scenario: 默认模式为混合检索

- **WHEN** 用户调用检索接口且未显式指定 mode
- **THEN** 系统按 hybrid 模式执行两条路径并返回 RRF 融合后的结果

### Requirement: 检索结果可回溯到原文

每条命中结果 MUST 至少给出材料标题、切片序号、字符区间与一段正文摘录，并提供打开对应材料的入口；摘录与标题 MUST 取自 MySQL 中的切片正文与材料记录，MUST NOT 来自向量库 payload。

#### Scenario: 命中携带完整出处

- **WHEN** 任一模式检索返回命中切片
- **THEN** 每条命中包含材料标题、切片序号、字符区间、正文摘录与该材料的访问入口，且摘录文本等于 MySQL 中该切片的 chunk_text

### Requirement: 无依据时不返回结果

当所选模式过滤后无任何候选切片时，系统 MUST 返回固定文案"资料中未找到相关内容"且 `hits` 为空列表，MUST NOT 以低相关切片凑数；空查询 MUST 返回 400。Qdrant 不可用时，vector 与 hybrid 模式 MUST 返回 503 且 MUST NOT 编造相似度分数，keyword 模式不受影响。

#### Scenario: 本班无相关内容

- **WHEN** 用户的提问与本班所有材料均无关
- **THEN** 系统返回 200，body 含固定文案"资料中未找到相关内容"，hits 为空数组

#### Scenario: 空查询被拒绝

- **WHEN** 检索请求的查询字符串为空或仅空白
- **THEN** 系统返回 400，不执行任何检索

#### Scenario: 向量库不可用时的降级

- **WHEN** Qdrant 不可用且用户以 vector 或 hybrid 模式检索
- **THEN** 系统返回 503 且不返回伪造的相似度分数；同一时刻 keyword 模式仍返回 200

### Requirement: 检索班级隔离由会话强制

学生与教师均可检索本班材料；检索过滤所用 `class_id` MUST 仅来自登录会话上下文，查询字符串、JSON 正文或请求头中携带的班级编号在解析后 MUST 被丢弃。MySQL 关键字查询与 Qdrant 向量查询 MUST 同时带班级条件，回 MySQL 取正文时 MUST 再次按会话班级核对。跨班级检索对外 MUST 表现为 200 + 空命中（或固定未找到文案），MUST NOT 以 403/404 暗示资料归属；按材料标识打开详情仍沿用第 3 课规则——跨班与不存在同构 404。

#### Scenario: 请求体伪造班级被忽略

- **WHEN** A 班用户登录后在检索请求体中写入 B 班的 class_id
- **THEN** 实际过滤条件为会话中的 A 班，结果不出现任何 B 班切片

#### Scenario: 两路均按会话班级过滤

- **WHEN** 用户以 hybrid 模式检索
- **THEN** MySQL 全文查询含 class_id=会话班级 且仅查 ready 切片，Qdrant 查询带同一 class_id 过滤，回表查询再次按该班级核对

#### Scenario: 跨班特有词汇检索表现为无命中

- **WHEN** A 班用户使用仅出现在 B 班正文中的词检索
- **THEN** 系统返回 200 与空命中（或固定未找到文案），不返回 403/404，也不出现 B 班切片

### Requirement: 教师按新策略重建索引

系统 SHALL 允许教师对本班材料发起索引重建：先删除该材料既有的切片与向量记录，再以本次请求指定的策略重新切分、嵌入与写入；重建 MUST NOT 影响其他材料的切片与向量。已入库材料 MUST NOT 因系统升级或配置变化被自动重新切分。

#### Scenario: 教师重建本班材料索引

- **WHEN** 教师对本班一份已入库材料以 hierarchy 策略发起重建
- **THEN** 该材料的旧切片与旧向量被删除并按新策略重新生成，材料文件与 body_text 不变，其他材料的切片与向量不受影响

#### Scenario: 学生不能重建索引

- **WHEN** 学生对任意材料发起索引重建
- **THEN** 系统返回 403，不删除或重建任何切片与向量

#### Scenario: 重建跨班材料被拒

- **WHEN** 教师对非本班材料发起索引重建
- **THEN** 系统返回与不存在同构的 404，不删除或重建任何数据

### Requirement: 有依据才生成的带出处问答

系统 SHALL 提供 `POST /ask`：仅以用户最新一句提问在本班内执行混合检索并取前 4 条切片；若无命中切片，接口 MUST 直接返回固定文案"资料中未找到相关内容"且 `citations` 为空，MUST NOT 调用对话生成网关。有命中时，对话模块的输入 MUST 仅包含材料标题、切片序号、切片正文、用户本轮提问（此前若干轮对话可附于其后）与按检索顺序排列的编号；回答正文 MUST 以 [1]、[2] 等标注引用，标注顺序与响应中出处列表顺序一致。系统 MUST NOT 向对话模块传递向量分量、向量库原始点数据或其他班级切片；客户端自行构造的 system 消息 MUST 被丢弃。本迭代 MUST NOT 实现流式输出。

#### Scenario: 有依据生成带编号引用的回答

- **WHEN** 已登录用户提问且本班混合检索得到至少一条命中切片
- **THEN** 系统调用对话网关生成简短回答，回答中的 [1]/[2] 标注与 citations 出处列表（材料标题、切片序号）顺序一一对应

#### Scenario: 无依据不调用生成模型

- **WHEN** 用户提问与本班材料无关、混合检索无候选
- **THEN** 接口返回固定文案且 citations 为空，对话网关未被调用

#### Scenario: 客户端注入 system 消息被丢弃

- **WHEN** 请求中包含客户端自行构造的 system 角色消息
- **THEN** 该消息不会传递给对话网关，生成过程只使用系统组装的提示词与用户提问

#### Scenario: 学生与教师均可提问

- **WHEN** 学生或教师携带有效会话调用 POST /ask
- **THEN** 两者均得到同等的本班检索与问答服务，班级范围仍只取自会话

### Requirement: 模型网关仅服务端可见

嵌入网关与对话网关的地址、密钥与调用过程 MUST 仅存在于服务端；浏览器 MUST 只能调用本站检索与问答接口，MUST NOT 获得网关密钥、原始网关响应或向量分量数据；页面与接口响应 MUST NOT 展示向量分量。

#### Scenario: 浏览器拿不到网关密钥与向量

- **WHEN** 用户在浏览器中完成检索与问答并检查本站接口的响应
- **THEN** 响应中仅包含命中的文本出处、摘录与回答文本，不含网关密钥、嵌入原始响应或任何向量分量
