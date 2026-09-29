# Design: add-traceable-vector-retrieval

## 背景与约束

- 现有技术栈：Flask 3 + PyMySQL + MySQL 8.0（第 3 课迁移完成），Compose 三服务 web(Nginx)/api(Flask)/db(MySQL)，仅 web 映射 8080；会话 cookie + 服务端每请求查库解析 `userId/role/classId`；上传走白名单（.txt/.md）与两表事务（materials + knowledge_entries）。课件的参考实现是 Go，本设计沿用本组 Flask 栈，行为契约以课件 `knowledge-retrieval` 规约为准。
- 模型能力来自课程网关 `https://ai-gateway.devops.hello1023.com/`（OpenAI 兼容接口），嵌入 `/embeddings`、对话 `/chat/completions`，密钥由环境变量注入，仅在服务端使用。
- 硬性边界：班级只从会话取；向量库不存正文；无依据不生成；Qdrant/网关故障时 keyword 必须可用；本课不做流式（第 5 课）、不引入 LangChain 等编排框架。
- API 路径沿用现有风格（`/materials`、`/auth/login` 均无 `/api` 前缀，Nginx 统一反代到 api 根），故本课接口为 `POST /search`、`POST /ask`，不采用课件示例里的 `/api/*` 前缀。

## 关键决策

### D1. Compose 四服务拓扑，新增 qdrant 仅内网

- 新增服务 `qdrant: qdrant/qdrant:v1.x`（REST 6333，容器内），无 `ports`，named volume `qdrant_data:/qdrant/storage`，`restart: unless-stopped`。
- `api.depends_on: qdrant` 只保证启动顺序；**不**把 Qdrant 纳入 api 启动就绪重试：第 3 课的 `_connect_with_retry` 仍只针对 MySQL。api 启动时"尽力"ensure collection（Qdrant 不通就跳过并记日志），保证 `/health` 200 与 keyword 检索不受影响。
- `web` 的 Nginx 不新增任何对 qdrant/网关的代理位置；浏览器只能到 api。

### D2. 迁移 003：knowledge_chunks + ngram 全文索引

新增 `migrations/003_knowledge_chunks.sql`，沿用 001/002 的幂等风格（`CREATE TABLE IF NOT EXISTS` + 内联 KEY）：

```
knowledge_chunks(
  id BIGINT AUTO_INCREMENT PK,
  material_id BIGINT NOT NULL,
  knowledge_entry_id BIGINT NOT NULL,
  class_id BIGINT NOT NULL,
  chunk_index INT NOT NULL,
  chunk_text MEDIUMTEXT NOT NULL,
  char_start INT NOT NULL, char_end INT NOT NULL,
  strategy VARCHAR(16) NOT NULL,           -- auto|custom|hierarchy
  index_status ENUM('ready','failed') NOT NULL DEFAULT 'ready',        -- 正文切片就绪（keyword 用）
  embedding_status ENUM('pending','ready','failed') NOT NULL DEFAULT 'pending', -- 向量状态
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY (material_id, chunk_index),
  KEY (class_id, index_status),
  FULLTEXT KEY ft_chunks_text (chunk_text) WITH PARSER ngram,   -- 内联全文索引
  FK material_id -> materials(id) ON DELETE CASCADE,
  FK knowledge_entry_id -> knowledge_entries(id) ON DELETE CASCADE,
  FK class_id -> classes(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- MySQL 8.0 的 `innodb_ngram_token_size` 默认就是 2，满足课件要求，无需额外启动参数。
- 删除材料时切片随 FK 级联删除；Qdrant 点由应用层在"删除材料/重建索引"路径显式删除（向量库不参与 DB 事务）。

### D3. 切分模块：纯函数、三策略、不改原文

`app/services/chunking.py`：

- 输入：预处理后文本 + 策略参数；输出 `list[Chunk(index, text, char_start, char_end)]`。
- `auto`：窗口 800、重叠 80；从窗口末端向前找最近的空行/换行/句号作为断点，找不到硬切；忽略请求中自定义长度。
- `custom`：窗口 100–2000、重叠 0–50%（非法值 400）；预处理选项 `strip_urls`、`strip_emails`、`collapse_spaces`，预处理仅作用于副本；返回的偏移基于预处理后文本。
- `hierarchy`：按 `^(#{1,3})\s+` 拆章，标题行并入本章；章长度超 800 时复用 auto 窗口切分并保持全章 chunk_index 连续。
- 确定性：同参数同文本输出完全一致，便于测试。

### D4. 嵌入与对话网关客户端

`app/services/model_gateway.py`：

- 两个独立函数 `embed_texts(texts) -> list[list[float]]`（批量，一次 HTTP 调用）与 `chat(messages) -> str`；base_url/api_key/model 全部来自 config；`requests.Session` 设置连接/读取超时（建议 5s/30s）与 Authorization Bearer。
- 定义两类异常：`GatewayUnavailable`（连接失败/超时/5xx/未配置）与 `GatewayRejected`（4xx 请求错误），供路由区分 503 与 400。
- 向量维度在首次成功嵌入时获得；ensure collection 时用该维度创建（cosine）。维度与既有 collection 不一致按显式错误处理（要求重建索引），不静默截断。

### D5. Qdrant 适配层：主键=切片 id，payload 不含正文

`app/services/vector_store.py`（基于官方 `qdrant-client`）：

- `ensure_collection(dim)`：不存在则 `recreate`/create，余弦；启动时 best-effort 调用。
- `upsert(chunks, vectors)`：point id 直接用 MySQL 自增 id（课程数据量远小于 uint64），payload 仅五个标识字段。
- `search(class_id, vector, limit, score_threshold=0.35)`：带 `Filter(must=[class_id])`。
- `delete_by_material(material_id)`：重建索引/材料删除时调用。

### D6. 上传后挂接索引：同步、尽力、失败可重建

- `upload.save_upload` 现有的"落盘→读全文→两表事务提交"保持不变；**事务提交成功后**调用新的 `indexing.index_material(material_id, strategy="auto")`：
  1. 读 knowledge_entries.content（预处理仅在切分函数内做副本，不回写）；
  2. 单事务插入全部 knowledge_chunks（index_status 直接 ready，embedding_status=pending）；
  3. 一次批量 embed；成功者 upsert Qdrant 并置 `embedding_status=ready`，失败/缺失的切片置 `embedding_status=failed`；`index_status` 恒为 `ready`，因此嵌入失败不影响关键字检索。
- 同步执行（本课不做异步队列，第 8 课才做）：材料文件 ≤50MB，切片数有限，嵌入走批量接口，延迟可接受；上传接口总超时由网关 client 的 30s 读超时约束。
- 索引阶段任何异常都不改变 201 结果：材料已提交即可见、可下载、可关键字检索，教师事后用重建索引补救向量。
- 启动种子流程在 `seed(conn)` 之后增加 `backfill_indexes(conn)`：对没有任何切片的 knowledge_entries 按 auto 建切片并尝试嵌入；已存在切片的材料永不自动重建。

### D7. 检索编排与 RRF

`app/services/retrieval.py`：

- 统一解析入口：`search(class_id, query, mode)`；`class_id` 形参只允许调用方传 `g.current_user["classId"]`，**不接受**请求体班级字段（路由层不把 body 中的 class_id 传入）。
- keyword：`MATCH(chunk_text) AGAINST (%s IN NATURAL LANGUAGE MODE)` + `WHERE class_id=%s AND index_status='ready'`，按返回相关度降序取 top 20。
- vector：embed 问句 → qdrant search（阈值 0.35、limit 20、班级 filter）→ 回 MySQL `WHERE id IN (...) AND class_id=<会话班级>` 二次核对并取正文。
- hybrid：两路独立得到有序 id 列表；RRF 分数 `Σ 1/(60 + rank)`（两路从 rank=1 起算），缺席路不贡献；融合后按分数降序取前 10，再统一回表组装结果。
- 结果 DTO：`{materialId, materialTitle, chunkId, chunkIndex, charStart, charEnd, excerpt, mode, score?}`；`excerpt` 取 `chunk_text`（可统一截断展示长度，如前后保留 200 字），再加 `materialUrl=/materials/{materialId}`。**不含**任何向量字段。
- Qdrant 抛连接类异常：vector 直接报 `RetrievalUnavailable`；hybrid 若 keyword 一路成功——按规约"依赖不可用"的模式选择：vector 路不可用属于该路"缺席"，RRF 可退化为单路排序。与规约"Qdrant 不可用时 hybrid 返回 503"对齐，**hybrid 在 Qdrant 不可用时返回 503**（不静默退化），只有显式 keyword 模式保证可用——规约原文如此，避免用户误以为混合结果完整。

### D8. /ask：检索组装提示词，模型只做受控生成

`app/services/answer.py` + `app/routes/ask.py`：

- 固定流程：hybrid 取前 4 条 → 0 条直接返回 `{answer:"资料中未找到相关内容", citations:[]}`，**不 import/调用** chat；
- 有命中时服务端组装 system 提示词（要求只用给定切片作答、每条事实后标 [n]、不得使用切片外知识），消息只含：system（服务端写死）、可选历史（清洗后仅保留 user/assistant 轮次，客户端传 system 一律丢弃）、user（问题 + 编号材料清单：标题/切片序号/正文）。
- 响应 `{answer, citations:[{materialTitle, chunkIndex, materialId}]}`，编号按 RRF 顺序 1..4。
- 不做流式：`chat()` 普通 JSON POST，响应一次性返回。

### D9. 重建索引接口

`POST /materials/<id>/reindex`：`@auth_required + @role_required("teacher")`；先按会话班级确认材料存在（不存在/跨班 → 同构 404），再 `vector_store.delete_by_material` + `DELETE FROM knowledge_chunks WHERE material_id=%s AND class_id=<会话班级>`，随后按 body 中策略（默认 auto，参数校验同切分模块）重新 `index_material`。学生 403。

### D10. 配置与环境变量

`app/config.py` 新增（全部带默认值，均非启动必需）：

```
QDRANT_HOST=qdrant  QDRANT_PORT=6333  QDRANT_COLLECTION=campusclaw_chunks
EMBED_BASE_URL / EMBED_API_KEY / EMBED_MODEL
CHAT_BASE_URL / CHAT_API_KEY / CHAT_MODEL
RETRIEVAL_VECTOR_THRESHOLD=0.35  RRF_K=60  SEARCH_PATH_LIMIT=20  SEARCH_FINAL_LIMIT=10  ASK_TOP_K=4
GATEWAY_TIMEOUT_CONNECT=5  GATEWAY_TIMEOUT_READ=30
```

`.env.example` 给出课程网关 base_url 与占位 key、每项注释；真实 key 只进 `.env`。未配置网关 key 时 embed/chat 抛 GatewayUnavailable → vector/hybrid/ask 返回 503，keyword 与系统其余功能 200。

### D11. 测试策略（离线可跑、不依赖真实网关）

- conftest 增加 Qdrant 测试配置（`QDRANT_HOST=qdrant`，测试 collection `campusclaw_chunks_test`，每测试重建）；测试 DB 迁移顺序追加 003。
- 嵌入/对话在测试中 monkeypatch `model_gateway`：fake embed 用"基于字符的确定性伪向量"（与文本一一对应、可体现词面重合），使同词/近义场景可断言；fake chat 回显固定模板（含 [1]）以验证编号与"无命中不调用"（用 spy 断言调用次数为 0）。
- 用例覆盖：三策略切分边界、custom 参数 400、偏移正确性；keyword 命中与不依赖 Qdrant；vector 阈值过滤与回表班级核对；RRF 双路命中靠前；跨班伪造 class_id 无效且返回 200 空；空查询 400；Qdrant down 时 keyword 200 / vector、hybrid 503；ask 无命中不调 chat、有命中 citations 对齐、system 注入被丢弃；嵌入失败 → 切片 failed + 材料 201；重建索引（教师 200/学生 403/跨班 404）。
- E2E：test-client 模式覆盖检索/问答主路径；HTTP 模式经 8080 验证浏览器可达接口形状。

### D12. 前端

Dashboard 在材料卡片下新增两块：①"知识库检索"（查询输入框 + mode 下拉 keyword/vector/hybrid + 结果卡片：标题、#序号、字符区间、摘录、"打开材料"链接、空命中固定文案）；②"知识库问答"（输入框 + 回答区 + 引用列表）。前端不保存/转发网关地址密钥，不渲染向量字段；403/503/400 按统一错误条展示。

## 风险与取舍

| 风险 | 处置 |
|------|------|
| 评测环境无法访问课程网关 | keyword 全链路离线可用；vector/ask 通过 env 配置即活；测试用 fake，不依赖外网 |
| 嵌入模型维度变更/与 collection 不符 | 首嵌获得维度并建集合；维度冲突显式报错并引导重建索引，不静默处理 |
| ngram 对单字/极短查询支持有限 | 课件指定 token=2，单字查询可能无命中，属预期；README/接口文档注明 |
| 同步索引拖长上传耗时 | 嵌入批量接口 + 30s 超时；失败不阻塞 201；第 8 课再演进为异步队列 |
| MySQL 与 Qdrant 数据不一致（删材料时向量残留） | 所有删除路径（材料删除、reindex）统一走应用层"先/后删向量"流程；payload 带 material_id 可兜底清理 |
| 跨班信息泄露 | 三路统一会话 class_id；Qdrant filter + MySQL 回表双重核对；跨班检索 200 空而非 404 |
