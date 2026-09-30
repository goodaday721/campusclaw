## 价值

为校园教学提供最小可用的身份认证、角色权限、班级数据隔离、知识库材料管理闭环，以及限定班级范围、可溯源的知识库检索与有依据问答，作为后续教学功能的安全底座。

## 场景

教师向本班知识库投放教学材料；学生与教师可在本班材料中按关键字/语义检索具体切片、查看出处并打开原文件，也可以就本班材料提问，系统只在资料中有依据时给出带来源标注的回答。

## 本学期不做

流式多轮对话助手、MCP 工具接入、作业提交与批改、异步任务队列、SSO/生产高可用。

## 快速开始（Docker Compose，唯一交付形态）

前置要求：仅安装 Docker Desktop（含 Docker Compose v2），无需 Python/MySQL 本机环境。

```bash
# 1. 准备环境变量（填写数据库密码等必填项）
cp .env.example .env
#    编辑 .env：DB_PASSWORD、DB_ROOT_PASSWORD、JWT_SECRET 必须改成你自己的值
#    （JWT_SECRET 可用 python -c "import secrets; print(secrets.token_hex(32))" 生成）
#    使用向量检索/问答还需填写 EMBED_API_KEY/EMBED_MODEL 与 CHAT_API_KEY/CHAT_MODEL

# 2. 一键构建并启动（web / api / db / qdrant 四服务）
docker compose up --build -d

# 3. 查看服务状态（四个服务均应为 running）
docker compose ps

# 4. 验证
#    健康检查：http://localhost:8080/health → {"status":"ok"}
#    登录页：  http://localhost:8080/login
```

> web 服务是唯一映射宿主机端口的入口（默认 8080，由 `.env` 的 `WEB_PORT` 控制）；
> api、MySQL 与 Qdrant 均只在 Compose 内部网络，宿主机无法直连。
> 模型网关（嵌入/对话）仅由 api 服务端调用，浏览器拿不到网关密钥，也不能直连向量库。

## 预置账号

首次启动时自动建库、迁移并写入以下演示数据（两个班、两份班级材料，种子材料自动按 auto 策略完成切片）：

| 账号 | 密码 | 角色 | 班级 |
| --- | --- | --- | --- |
| teacher_a | teacher_a_pass | 教师 | A班 |
| student_a | student_a_pass | 学生 | A班 |
| teacher_b | teacher_b_pass | 教师 | B班 |
| student_b | student_b_pass | 学生 | B班 |

## 认证方式（JWT Bearer Token）

登录采用 token 方案：`POST /auth/login` 校验账号密码后签发 **HS256 JWT**（payload 仅含
`sub`/`jti`/`iat`/`exp`，不含角色与班级），token 存于浏览器 `localStorage`，后续请求全部携带
`Authorization: Bearer <token>` 请求头；服务端同时将 `jti` 登记到 `sessions` 表以支持即时撤销。
角色与班级每次请求都从数据库实时读取，token payload 声明一律忽略。

```bash
# 登录：响应体返回 token 与用户信息（不使用 Cookie）
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"teacher_a","password":"teacher_a_pass"}'

# 调用受保护接口：携带 Authorization 请求头
curl http://localhost:8080/materials -H "Authorization: Bearer <登录返回的token>"

# 登出：服务端删除会话记录，原 token 立即失效
curl -X POST http://localhost:8080/auth/logout -H "Authorization: Bearer <token>"
```

浏览器行为：登录后 token 自动保存并在页面内自动附带；退出登录会同时撤销服务端会话并清除本地 token。
`JWT_SECRET` 是 token 签名密钥（`.env` 必填项），更换后所有已签发 token 立即失效，需重新登录。

## 知识库检索与问答（第 4 课）

登录 Dashboard 后可使用「知识库检索」与「知识库问答」两块功能；接口同样可直接调用：

- `POST /search`：body `{"query": "...", "mode": "keyword|vector|hybrid"}`，默认 hybrid。
  每条命中返回材料标题、切片序号、字符区间、正文摘录与打开材料链接，全部只限本班。
- `POST /ask`：body `{"question": "...", "history": [...]}`；先在本班混合检索取前 4 条切片，
  无依据时返回固定文案「资料中未找到相关内容」且 `citations` 为空（不调用对话模型）；
  有依据时回答以 [1][2] 标注，标注顺序与 citations 一致。
- `POST /materials/<id>/reindex`：教师可按 auto/custom/hierarchy 策略重建本班材料索引。

实现要点：

- 正文切为切片存入 MySQL `knowledge_chunks`（ngram 全文索引，token=2）；**向量库只存向量与标识，不存正文**。
- 关键字检索只查 MySQL（不依赖向量库/模型网关）；向量检索余弦相似度阈值 0.35；
  混合检索两路独立过滤后按 RRF（k=60）融合。
- 检索班级只取自登录 token 解析出的实时身份（数据库读取）；请求体伪造 class_id 一律无效；跨班检索表现为 200 + 空命中。
- 上传材料事务提交后才执行切分/嵌入；索引失败不影响已提交材料，切片标记 `failed`，可由教师重建。

### 模型网关配置（可选，只影响向量/问答）

在 `.env` 中填写课程 OpenAI 兼容网关配置：`EMBED_BASE_URL`、`EMBED_API_KEY`、`EMBED_MODEL`、
`CHAT_BASE_URL`、`CHAT_API_KEY`、`CHAT_MODEL`（地址默认指向课程网关，密钥只进本地 `.env`）。
**未配置密钥时系统完全正常启动**：关键字检索、上传下载、认证授权均可用；
向量/混合检索与问答返回 503 并提示依赖不可用。

## 数据持久化与重置

- MySQL 数据存放在 named volume `mysql_data`，Qdrant 向量数据存放在 named volume `qdrant_data`，上传文件挂载在宿主机 `./uploads`。
- `docker compose down` 后再 `docker compose up`（**不带** `-v`）：全部账号、会话、材料、切片与向量数据保留。
- `docker compose down -v` 会删除数据卷、清空数据库与向量库（下次启动自动重建并重新预置种子数据），**只能用于主动重置环境**，不能作为常规重启方式。
  注意：`down -v` 不清除 `./uploads` 中已上传的文件，如需彻底重置可手动清空该目录。

## 单实例部署声明

**本迭代仅支持单实例部署。** 上传文件、MySQL 与 Qdrant 数据均存放于单机数据卷、运行状态按单进程设计，未针对多副本/横向扩展做共享存储与状态一致性设计；多副本部署会出现数据与状态不一致，不在支持范围内。限流与生产级高可用（MySQL/Qdrant 主从、多副本负载均衡）均属本学期不做项。

## 运行测试

```bash
# 标准路径：容器内跑（直连内部网络 db/qdrant，无需宿主机端口；网关以离线 fake 替代）
docker compose exec api pytest

# 端到端场景回归（test-client，容器内）
docker compose exec api python e2e_test.py

# 端到端场景回归（HTTP，经 web 入口 8080；未配置网关密钥时向量/问答项按 503 验收）
python e2e_test.py --http
```

## 技术栈

Flask + MySQL 8.0（PyMySQL，ngram 全文索引）+ Qdrant 向量库 + OpenAI 兼容模型网关（仅服务端）+ Nginx 反向代理；Docker Compose 四服务编排（web / api / db / qdrant），仅 web 映射宿主机端口。
