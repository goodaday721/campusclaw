# Tasks: add-traceable-vector-retrieval

## 1. 基础设施与配置

- [x] 1.1 `requirements.txt` 新增 `qdrant-client` 与网关 HTTP 调用依赖；verify: 干净镜像 `docker compose build api` 成功，容器内 `python -c "import qdrant_client, requests"` 可用
- [x] 1.2 `docker-compose.yml` 新增 `qdrant` 服务（官方镜像、无 ports、named volume `qdrant_data`、仅内网、restart 策略），api `depends_on` 追加 qdrant；verify: `docker compose config` 无告警，`up -d` 后 `docker compose ps` 四服务 Up，PORTS 列仅 web 有宿主机映射，宿主机直连 qdrant 6333 拒绝
- [x] 1.3 `app/config.py` 新增 Qdrant、嵌入网关、对话网关与检索阈值配置（均有默认值、非启动必需）；`.env.example`/`.env` 增加对应占位项与注释（课程网关 base_url、占位 key、阈值 0.35、RRF k=60）；verify: 未填写网关 key 时 api 正常启动且 `/health` 200；`.env.example` 无真实密钥

## 2. 数据层

- [x] 2.1 新增 `migrations/003_knowledge_chunks.sql`：knowledge_chunks 表（chunk_text MEDIUMTEXT、chunk_index、char_start/char_end、strategy、index_status ENUM、material+index 唯一键、班级索引、`FULLTEXT ... WITH PARSER ngram` 内联、级联外键）；verify: 对空库连续执行 001/002/003 两次无报错、无重复对象，`SHOW INDEX` 可见 ngram 全文索引
- [x] 2.2 新增 `app/repositories/chunks.py`：按 material 插入切片（同事务批量）、按 material 删除、按 id+class 回表查询、列出缺切片的 entries（供启动回填）；verify: pytest——切片 CRUD、级联删除、回表带 class_id 二次过滤用例通过

## 3. 切分、嵌入与入库编排

- [x] 3.1 新增 `app/services/chunking.py`：auto（800/80、空行/换行/句号优先断点）、custom（100–2000、0–50%、非法参数报错、URL/邮箱移除与空白折叠预处理）、hierarchy（# / ## / ### 分章、标题随章、超长再窗口切）；输出含序号与基于预处理文本的字符区间；verify: pytest——三策略切分结果、重叠、偏移、边界值 400、确定性（同输入两次输出一致）
- [x] 3.2 新增 `app/services/model_gateway.py`：OpenAI 兼容 `embed_texts`（批量）与 `chat`，Bearer 鉴权、超时、`GatewayUnavailable`/`GatewayRejected` 分类异常，未配置 key 抛 GatewayUnavailable；verify: pytest——用 fake HTTP 层验证请求形状（密钥不出现在日志）、超时/5xx 归类、4xx 归类
- [x] 3.3 新增 `app/services/vector_store.py`：ensure collection（余弦、维度取自首嵌）、upsert（point id=knowledge_chunks.id，payload 仅五个标识字段、无正文）、按 class_id+阈值 0.35 检索、delete_by_material；verify: pytest（真实 Qdrant 测试 collection）——写入后按班级能检出、他班过滤为空、删除后点消失
- [x] 3.4 新增 `app/services/indexing.py`：`index_material(material_id, strategy, ...)`——单事务写切片（index_status=ready、embedding_status=pending）→ 批量嵌入 → 成功的 upsert 并置 embedding ready、失败仅置 embedding failed 且不写向量（关键字路径不受影响）；`reindex_material` 先删向量与切片再重建；`backfill_indexes` 仅为无切片材料补 auto 索引；verify: pytest——全成功路径 embedding ready+点齐全、嵌入网关失败时材料保留且 embedding failed 无向量点、失败后 keyword 仍命中、重建后旧点全部清除
- [x] 3.5 `app/services/upload.py` 在两表事务提交成功后挂接 `index_material(auto)`，索引异常不影响 201；`app/__init__.py` 启动流程在 seed 后调用 `backfill_indexes`（best-effort，不阻塞启动）；verify: pytest——上传成功后切片可被 keyword 检出；断网/未配 key 时上传仍 201、材料可下载；pytest——干净库启动后种子材料均有 auto 切片，重启不重复切分

## 4. 检索与问答接口

- [x] 4.1 新增 `app/services/retrieval.py`：keyword（`MATCH ... AGAINST IN NATURAL LANGUAGE MODE` + class_id + ready 过滤）、vector（嵌入→Qdrant 班级过滤+0.35 阈值→回 MySQL 带班级核对取正文）、hybrid（两路独立过滤后 RRF k=60 融合、缺席路不贡献分、取前 10），结果 DTO 含材料标题/切片序号/字符区间/摘录/材料链接且不含向量字段；空查询抛 400 类错误，Qdrant/嵌入不可用抛 RetrievalUnavailable；verify: pytest——同词命中、语义近义命中、阈值丢弃、双路同中排名靠前、跨班回表核对、结果字段齐全
- [x] 4.2 新增 `app/routes/search.py` 注册 `POST /search`：`@auth_required`，学生教师可用；body 仅取 query/mode（class_id 一律不读取），mode 默认 hybrid；空查询 400、Qdrant/网关不可用时 vector/hybrid 返回 503（keyword 仍 200）、无命中返回固定文案与 hits:[]；verify: pytest + e2e——三种模式返回结构一致，请求体伪造 class_id 无效且跨班特有词返回 200 空命中
- [x] 4.3 新增 `app/services/answer.py` 与 `app/routes/ask.py` 注册 `POST /ask`：hybrid 取前 4 条；0 条直接返回固定文案 + citations:[] 且不调用 chat（spy 验证）；有命中时服务端组装 system 提示词（仅依据切片作答、[n] 标注），历史只保留 user/assistant 且丢弃客户端 system，回答编号与 citations 顺序一致，非流式；网关不可用 503；verify: pytest——有命中 [1]/[2] 对齐、无命中零调用、注入 system 被丢弃、citations 只含本班
- [x] 4.4 新增 `POST /materials/<id>/reindex`：教师 + 会话班级双重校验，学生 403、跨班/不存在同构 404；verify: pytest——教师重建成功（旧切片/旧向量清空、新策略生效、他材料不受影响）、学生 403、跨班 404

## 5. 前端

- [x] 5.1 `app/routes/pages.py` Dashboard 增加检索区（查询框 + keyword/vector/hybrid 模式选择）与结果卡片（标题、切片序号、字符区间、摘录、打开材料链接、空命中固定文案、503/400 错误提示）；verify: 浏览器以 teacher_a/student_a 登录检索，三种模式结果正确渲染，结果中无向量字段
- [x] 5.2 Dashboard 增加问答区：提问框、回答文本、引用列表（与 [n] 对应、可点开材料）、无依据固定文案；前端只调用 `/search`、`/ask`；verify: 浏览器问答主路径可用，DevTools 网络面板确认无任何对 qdrant 或模型网关域名的直连请求

## 6. 测试设施、文档与端到端验收

- [x] 6.1 `tests/conftest.py` 扩展：测试 DB 迁移追加 003；新增 Qdrant 测试 collection（每测试重建）与 model_gateway 的确定性 fake（伪嵌入 + chat spy）；verify: `docker compose exec api pytest` 全量通过，测试全程不访问外网
- [x] 6.2 `e2e_test.py` 增加 test-client 与 HTTP 模式用例：上传→检索（三种模式）→问答引用→跨班空命中→无依据文案→重建索引；verify: 两种模式全部检查项通过
- [x] 6.3 `README.md` 更新：四服务拓扑图与端口表、Qdrant/网关环境变量说明（含课程网关配置方式）、检索/问答接口与三种模式、降级行为（Qdrant/网关不可用的影响）、延续"仅支持单实例部署"声明；verify: 按 README 在干净环境从零 `cp .env.example .env` → `up --build -d` 可跑通检索主路径
- [x] 6.4 全量回归与留痕：四服务 `docker compose ps`、宿主机直连 6333/5000/3306 拒绝、8080 检索/问答 200、down→up（不带 -v）切片与向量数据保留、down -v 重置；verify: `openspec validate add-traceable-vector-retrieval --strict` 通过，pytest + e2e 逐条执行留痕
