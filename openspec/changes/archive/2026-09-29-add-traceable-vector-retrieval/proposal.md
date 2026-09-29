# Proposal: add-traceable-vector-retrieval

## Why

第 3 课完成了认证授权、班级隔离与材料正文入库，但入库的正文尚不能被检索：学生与教师无法用一句自然语言在本班材料中定位依据。第 4 课要求在同一套系统上增加可追溯的知识库检索——切分、嵌入、关键字/向量/混合三种检索，命中结果必须能回溯到具体材料的具体切片，并在此基础上提供"先检索、有依据才生成"的简短问答；本班材料中不存在依据时明确告知未找到，不得编造出处。

## What Changes

- 新增切片管线：材料上传事务提交后，将 `knowledge_entries` 正文按策略切分为切片写入 MySQL `knowledge_chunks` 表（切片序号、字符区间、正文索引状态 `index_status`、向量嵌入状态 `embedding_status`），默认 `auto` 策略（约 800 字窗口、约 10% 重叠，优先在空行/换行/句号断开），另支持 `custom`（100–2000 字、0–50% 重叠、可选去 URL/邮箱与折叠空白）与 `hierarchy`（按 Markdown 标题分章，超长章再按窗口切）。切片正文落库后 `index_status` 恒为 ready，关键字检索不依赖嵌入是否成功。
- 新增嵌入与向量存储：每个 ready 切片经服务端调用课程网关的 OpenAI 兼容 `/embeddings` 接口转为向量，写入 Compose 内新增的 **Qdrant** 服务（collection `campusclaw_chunks`，余弦度量）；向量主键等于 `knowledge_chunks.id`，payload 仅含 `class_id/material_id/knowledge_entry_id/chunk_id/chunk_index`，**不存正文**。嵌入失败时材料、正文与切片（index_status=ready）保留，仅 `embedding_status` 置 failed，不写不完整向量。
- 新增三种检索模式 `POST /search`（mode: `keyword`/`vector`/`hybrid`，默认 hybrid）：
  - `keyword`：仅查 MySQL `FULLTEXT ... WITH PARSER ngram`（ngram token 长度 2）且只查 `index_status=ready`；
  - `vector`：问句嵌入后在 Qdrant 按会话 `class_id` 过滤，余弦相似度低于 0.35 丢弃，再以向量主键回 MySQL 取正文；
  - `hybrid`：两路各自过滤后按 RRF（k=60）融合名次，缺席的一路不贡献分数。
  - 每条命中返回材料标题、切片序号、字符区间与正文摘录（摘录取自 MySQL），并可打开对应材料；无候选时返回固定文案"资料中未找到相关内容"且 `hits` 为空；空查询 400；Qdrant 不可用时 keyword 仍可用，vector/hybrid 返回 503，不编造分数。
- 新增有依据问答 `POST /ask`：先以混合检索取本班前 4 条切片；一条都没有则直接返回固定文案、`citations` 为空且**不调用对话网关**；有命中时把材料标题、切片序号、切片正文与本轮提问（可附此前轮次）交给对话网关生成简短回答，回答以 [1][2] 标注出处且标注顺序与出处列表一致；客户端注入的 system 消息一律丢弃；本课不做流式输出。
- 检索侧班级隔离：学生与教师均可检索本班；`class_id` 仅取自登录会话，请求参数/正文/请求头中自带的班级编号解析后一律丢弃；MySQL 与 Qdrant 两条路径都按班级过滤，回表时再次核对；跨班检索对外表现为 HTTP 200 + 空命中（不用 403/404 暗示资料归属），材料详情跨班仍沿用第 3 课的同构 404。
- 新增教师重建索引能力：教师可对本班材料按新策略重建索引（先删旧切片与旧向量，再重新切分嵌入）；切换策略不影响其他材料。
- **BREAKING** Compose 由三服务变为四服务：新增内部服务 `qdrant`（仅内网，不映射宿主机端口，named volume 持久化）；api 启动不再因 Qdrant 未就绪而阻塞（keyword 检索在 Qdrant 宕机时仍须可用）。
- 新增服务端环境变量：Qdrant 连接配置、嵌入网关与对话网关的 base_url/api_key/model（密钥仅存于 `.env`，`.env.example` 只给占位与说明，绝不下发浏览器）；启动时对种子材料按 auto 策略补齐索引。
- 前端 Dashboard 增加检索框（模式选择）与问答框，命中结果展示出处信息与"打开材料"链接，无依据时显示固定文案。

## Capabilities

### New Capabilities

- `knowledge-retrieval`: 班级范围内的正文切分、嵌入入库、关键字/向量/混合检索、出处溯源、索引重建，以及"先检索后生成、无依据不回答"的有引用问答。

### Modified Capabilities

- `knowledge-materials`: 上传成功后的可观察行为延伸——文件与 `knowledge_entries` 事务提交后，追加"切分→嵌入→写 Qdrant"的索引步骤；索引失败不影响已提交的材料与正文，切片以 `index_status=failed` 标记。原两表事务、白名单、孤儿清理等行为不变。
- `app-runtime`: Compose 编排由三服务变为四服务（新增仅内网可达的 Qdrant）；网络暴露控制覆盖 Qdrant；敏感环境变量范围扩展到嵌入/对话网关凭据与 Qdrant 配置。

## Non-Goals

- 不做流式输出与长对话编排（第 5 课内容）；本迭代 `/ask` 为一次性 JSON 响应，仅附带可选的有限历史轮次。
- 不做检索结果重排序（cross-encoder rerank），不引入 LangChain、LlamaIndex 等编排框架。
- 不做异步任务与消息队列（第 8 课内容）；切分与嵌入在上传/重建请求内同步完成。
- 不扩展上传文件白名单（仍仅 `.txt`/`.md`），不新增 PDF/Word/图片等二进制解析。
- 不做 MCP/工具接入（第 6 课）、作业提交与批改流程（第 7 课）。
- 不做 Qdrant、模型网关或 api 的高可用/多副本；延续单实例部署声明，向量数据与上传文件均为单机持久化。
- 不把切片正文存入向量库，不在浏览器暴露向量分量、网关密钥或网关原始响应。

## Impact

- **数据层**：新增迁移 `migrations/003_knowledge_chunks.sql`（`knowledge_chunks` 表 + `FULLTEXT ... WITH PARSER ngram` 索引、外键与 `index_status`）；新增 `app/repositories/chunks.py`。
- **基础设施**：`docker-compose.yml` 新增 `qdrant` 服务（内部网络 + named volume `qdrant_data`，api `depends_on` qdrant 但就绪失败不阻塞启动）；`requirements.txt` 新增 `qdrant-client` 与 HTTP 客户端依赖。
- **应用层**：新增 `app/services/chunking.py`、`model_gateway.py`（嵌入与对话客户端）、`vector_store.py`、`indexing.py`、`retrieval.py`（含 RRF）、`answer.py`；新增 `app/routes/search.py`（`POST /search`）、`app/routes/ask.py`（`POST /ask`）与教师重建索引路由；`app/services/upload.py` 在事务提交后挂接索引步骤；`app/config.py` 新增 Qdrant/嵌入/对话配置；`.env.example`/`.env` 补占位项。
- **种子**：启动初始化在迁移与种子之后对种子材料按 auto 策略补齐切片与向量。
- **前端**：`app/routes/pages.py` Dashboard 增加检索与问答 UI；浏览器只调用本站 `/search`、`/ask`，不持有网关密钥、不展示向量分量。
- **测试**：`tests/` 新增切分、三路检索、RRF、溯源、班级隔离、无依据不生成、Qdrant 降级等用例；嵌入/对话网关在测试中以受控 fake 替代，Qdrant 使用 compose 内实例与测试 collection。
- **文档**：README 更新四服务拓扑、新环境变量、网关配置说明与"仅支持单实例部署"声明的延续。
