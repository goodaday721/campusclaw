# Tasks: add-mcp-tool-integration

## 1. mcp-server（同仓独立服务）

- [x] 1.1 新增 `mcp-server/`：`server.py`（Flask：`POST /mcp` JSON-RPC 2.0 分发 initialize/tools/list/tools/call，`GET /health`；Bearer 校验失败 401；非法 JSON/缺 method/未知 method 返回 -32700/-32600/-32601 可读错误）、`tools.py`（`formula_hint`：关键词匹配公式/步骤提示，只给提示不给最终答案；`unit_convert`：常见长度/重量单位换算）、`requirements.txt`、`Dockerfile`（gunicorn 启动）
  - verify: 容器内 `curl -s -H "Authorization: Bearer $MCP_AUTH_TOKEN" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' localhost:8090/mcp` 返回两个工具；无令牌 401；`/health` 200
- [x] 1.2 `docker-compose.yml` 增 `mcp-demo` 服务（仅内网，不映射宿主端口）；`.env.example` 增 `MCP_AUTH_TOKEN` 说明
  - verify: `docker compose config` 通过；`docker compose up -d mcp-demo` 后 api 容器内可达 `http://mcp-demo:8090/health`

## 2. 数据层与仓储

- [x] 2.1 新增 `migrations/005_mcp.sql`：`mcp_servers`（class_id+name 唯一、base_url、token、status）、`mcp_tools_cache`（server_id 级联删除、name、description、input_schema JSON）、`mcp_call_logs`（class_id、server_id 可空、server_name、tool_name、status、detail、user_id、conversation_id、round_no、created_at）；`app/__init__.py`、`tests/conftest.py`、`seeds/seed.py` 的 MIGRATIONS 追加
  - verify: 容器内 pytest 后 `SHOW TABLES` 含三张新表；重复运行迁移不报错
- [x] 2.2 新增 `app/repositories/mcp.py`：servers（list/find_by_name/find/create/update/delete）、tools_cache（replace_all/list_by_server/list_for_class）、call_logs（append/list_by_class）；全部 SQL 参数化、班级条件强制
  - verify: pytest 经路由间接覆盖；`docker compose exec -T api pytest -q` 现有用例零回归
- [x] 2.3 `seeds/seed.py` 追加：每班预登记 `campus-tools`（`http://mcp-demo:8090`，token 取 `MCP_AUTH_TOKEN` 环境变量，未配置则跳过）；不自动连接
  - verify: 重启后登记仍在（DB 持久化）；重复 seed 不重复插入；列表响应只含 hasToken 布尔值

## 3. MCP 客户端与宿主服务

- [x] 3.1 新增 `app/services/mcp_client.py`：`initialize`/`list_tools`/`call_tool`（requests POST JSON-RPC，Bearer 令牌）+ 错误类 `McpUnavailable`（不可达/超时/5xx）、`McpRejected`（401/4xx）、`McpToolError`（JSON-RPC error 或 isError=true）
  - verify: pytest 单测：fake 响应下三方法正确解析；401 抛 McpRejected；isError=true 抛 McpToolError
- [x] 3.2 新增 `app/services/mcp_service.py`：引用解析与四查校验（格式/存在/已连接/在清单内）、工具声明构建（候选集：工具名→ref 映射）、指令式句式安全检查（命中整条丢弃换固定说明）、审计落库辅助
  - verify: pytest：合法引用过检；大写/连字符/缺 @ 400；未连接与清单外各报可读错误；句式检查命中返回固定说明

## 4. 路由层

- [x] 4.1 新增 `app/routes/api_mcp.py`：`GET/POST /api/mcp/servers`、`PUT/DELETE /api/mcp/servers/{id}`（同名再登记 409；响应只含 hasToken；删除时记录 server_id 置空但 server_name 保留）、`POST /api/mcp/servers/{id}/connect`（握手+发现+整体替换+置 connected；失败清缓存置 disconnected 并返回可读原因）、`POST /api/mcp/servers/{id}/disconnect`（清缓存+disconnected）、`GET /api/mcp/servers/{id}/tools`（缓存清单）、`GET /api/mcp/call-logs`（本班倒序审计）；学生一律 403；跨班 id 与不存在一致 404
  - verify: pytest：教师 CRUD+连接+断开全链路；学生 403；B 班教师访问 A 班 404；列表响应无令牌字符串；断开后 tools 为空
- [x] 4.2 `app/routes/api_skills.py` 保存前校验「工具」行引用（4.2 与 3.2 四查）：不合法/未登记/未连接/清单外均 400 可读错误
  - verify: pytest：`formula_hint@campus-tools` 连接后保存 201；断开后同 source 400；`Formula_Hint@x`/`formula-hint@x`/`formula_hint` 均 400
- [x] 4.3 `app/__init__.py` 注册 mcp 蓝图
  - verify: `/health` 200 且 `url_map` 含全部新端点

## 5. 调用循环编排

- [x] 5.1 `app/services/model_gateway.py` 新增 `chat_with_tools(config, messages, tools)`（非流式带 tools，返回 `{content, tool_calls:[{id,name,arguments}]}`）；现有 chat/chat_stream 不动
  - verify: pytest fake：返回 tool_calls 时正确解析；无 tools 参数时行为与 chat 一致
- [x] 5.2 `app/services/chat.py` 扩展 `_prepare`（构建候选集与声明）与 `start`（有候选工具时进入循环：`chat_with_tools` → 校验参数 → 带令牌 tools/call → 审计落库 → 结果数据段拼用户消息 → 最多 3 轮/累计 5 次 → 超限优雅降级）→ 最终流式收尾轮（不带 tools）
  - verify: pytest：命中工具的技能提问后 meta.tool_calls 含 ref/status/text/round；审计表新增 ok 记录；工具结果文本出现在收尾轮消息的数据段；上限调小后停止调用且仍能作答
- [x] 5.3 `chat.sse_stream` meta 事件新增 `tool_calls`（仅在确有调用时出现，先于任何 delta；无调用则省略该键）；denied/error 场景状态如实呈现，不静默成功
  - verify: pytest：SSE 帧序列 meta（含 tool_calls）→ delta* → done；技能无 MCP 工具时 meta 无 tool_calls 键；服务器断开后同技能提问 meta 中该调用 status=denied

## 6. 接口文档与前端

- [x] 6.1 `app/routes/api_docs.py` 补充 MCP 全部端点与错误码到 `/openapi.json`
  - verify: `curl -s localhost:5000/openapi.json | python -m json.tool` 合法；Swagger 页可见并试调 connect/tools/技能保存
- [x] 6.2 `pages.py` 教师侧新增「MCP 工具服务」卡（登记表单令牌框 type=password 提交后清空、连接/断开、已发现工具、最近调用记录）；对话页渲染 meta.tool_calls 工具栏（先于正文、显示 ref 与状态）
  - verify: 浏览器：教师登记→连接→看到工具；学生提问命中工具技能，回答开始前看到工具调用状态；列表页搜不到令牌原文

## 7. 测试与 e2e

- [x] 7.1 新增 `tests/test_mcp.py`（+conftest fake MCP 客户端与 fake chat_with_tools）：覆盖 1.1/3.1/3.2/4.1/4.2/5.1–5.3 全部场景；既有 106 例零回归
  - verify: 容器内 `docker compose exec -T api pytest -q` 全过
- [x] 7.2 `e2e_test.py` 追加第 6 课场景：连接 fake MCP → 注册含 `formula_hint@…` 的技能 → 学生提问 → 断言 meta.tool_calls、审计落库、断开后 denied
  - verify: 容器内 `python e2e_test.py` 与宿主机 `python e2e_test.py --http` 全过

## 8. apitest 与收尾

- [x] 8.1 `apitest/cases/` 增加 MCP 用例：登记（含重复 409）、列表（无令牌断言）、连接、列出工具、断开、非教师 403、全链路（连接→技能含引用→提问→call-logs 出现 ok）
  - verify: `docker compose exec -T api python apitest/run_all.py` 全过并生成报告；`git status` 不出现 report.html
- [x] 8.2 README 增补：MCP 工具服务与调用能力、`MCP_AUTH_TOKEN` 配置、验证路径；浏览器全链路验证（教师配置→学生触发工具→审计可查→断开后被拒）
  - verify: 按 README 步骤在新环境可完成一次带工具调用的学生提问
- [x] 8.3 `openspec validate add-mcp-tool-integration --strict` 通过，tasks 全部勾选后提交（不归档）
  - verify: 命令退出码 0；`git log` 含本变更 commit
