# 测试规范

适用范围：`tests/`、`e2e_test.py`、`apitest/`。三层测试各司其职，任何一层红灯都算未完成。

## 三层测试职责

- pytest（`tests/`，容器内跑）：单元 + 集成。用例直接经 Flask test client 打路由，断言状态码、响应体与数据库落库。
  检查：`docker compose exec -T api python -m pytest -q`。
- e2e（`e2e_test.py`）：按课程场景顺序回归（认证、隔离、上传、检索、问答、助手、工具）。容器内用 test client，宿主机 `--http` 经 8080 入口。
  检查：`docker compose exec -T api python e2e_test.py`；`python e2e_test.py --http`。
- apitest（`apitest/run_all.py`）：一接口一脚本、经 Nginx 真链路（`http://web:80`），每条断言状态码、响应内容、数据库一致性三层。
  检查：`docker compose exec -T api python apitest/run_all.py`，生成 `apitest/report.html`（已 gitignore）。
- 新增接口必须同时落三处：pytest 用例、`apitest/cases/` 脚本、README 验证路径。
  检查：`ls apitest/cases` 每个目录对应一个接口路径（`GET.py`/`POST.py`/`PUT.py`/`DELETE.py`），新增接口须补对应目录。

## 用例组织：正常 / 失败 / 边界

- 每个行为至少三条用例：正常路径一条、失败路径一条（越权或非法输入）、边界一条（空串、超限、恰好等于阈值）。
  检查：抽查 `tests/test_materials.py`（`TestUploadMaterial` 正常、`TestUploadConstraints` 失败与边界）与 `tests/test_mcp.py`（`TestRegistryAPI` 正常、`400/409` 失败）。
- 失败用例必须断言"没有副作用"：不落盘、不写库、不改状态。
  检查：`tests/test_materials.py::TestUploadConstraints` 断言 `materials` 与 `knowledge_entries` 无新记录；`tests/test_isolation.py::TestDirectURLBypass`。
- 鉴权类用例必须同时测 401（无 token）与 403（角色不符），且覆盖绕过前端直调。
  检查：`tests/test_auth.py::TestAuthRequired`、`tests/test_role.py::TestBypassFrontend`。
- 流式相关用例断言事件序列：`meta`（确有调用时含 `tool_calls`）→ `delta*` → `done`，顺序不可乱。
  检查：`tests/test_assistant.py::TestConversationsAPI::test_sse_hit_flow`、`tests/test_mcp.py::TestToolLoop`。

## 数据隔离

- 每个用例用 `test_db` fixture 重建 `campusclaw_test` 库并重跑全部迁移与种子；向量用 `campusclaw_chunks_test` collection，用例前删除重建。
  检查：`tests/conftest.py::test_db`、`tests/conftest.py::reset_vector_store`。
- 固定使用两个班与四个账号（`teacher_a`/`student_a` 属 A 班，`teacher_b`/`student_b` 属 B 班），跨班断言一律用 A 班查 B 班。
  检查：`tests/conftest.py` 的登录 fixture 与 `tests/test_isolation.py::TestCrossClassRejection`。
- 会话不跨用例复用：每个用例在重建库之后经 API 新建会话，不共享全局 `conversation_id`；跨班断言用 A 班账号访问 B 班会话与材料，期望 404。
  检查：`tests/test_assistant.py::TestConversationsAPI` 每个用例内自建会话；`tests/test_assistant.py::TestConversationsAPI::test_cross_class_message_404`。
- 用例不得连业务库或业务 collection；`TEST_DB_*` 由 compose 注入，`TEST_QDRANT_COLLECTION` 默认 `campusclaw_chunks_test`。
  检查：`docker compose config` 中 api 服务的 `TEST_DB_NAME`、`TEST_QDRANT_HOST`；`grep -n "campusclaw_chunks_test" tests/conftest.py`。
- 网关与 MCP 全部用离线 fake，测试不得发外网请求。
  检查：`tests/conftest.py` 的 `_fake_embed_texts`、`mcp_client_spy`、`chat_with_tools_spy`；`grep -rn "api_key" tests/` 无真实密钥。

## 一键运行

- 标准路径（容器内，推荐）：`docker compose exec -T api python -m pytest -q`。
  检查：退出码 0，输出无 `failed`。
- 容器内 e2e：`docker compose exec -T api python e2e_test.py`；宿主机 HTTP 版：`python e2e_test.py --http`。
  检查：两条命令最后均打印全 PASS。
- 接口回归：`docker compose exec -T api python apitest/run_all.py`。
  检查：脚本退出码 0，`apitest/report.html` 内无 FAIL 行。

## 通过判定

- 失败即阻断：任何一条用例失败、任何一层命令回到非 0，本变更不得合并、不得归档。
  检查：`docker compose exec -T api python -m pytest -q; echo $LASTEXITCODE` 必须为 0。
- 不允许用 `skip` / `xfail` / 注释掉断言来"通过"；确需跳过须在评审记录写原因与补救计划。
  检查：`docker compose exec -T api python -m pytest -q -rs` 输出的 skip 列表为空或与本例外记录一致。
- 现有用例零回归是新变更的硬门槛，不允许为迁就新行为改动既有断言。
  检查：`git diff tests/` 中既有断言只增不改；`docker compose exec -T api python -m pytest -q`。
- apitest 的 `SKIP` 只允许用于登录失败或缺少上游上下文，不得掩盖断言失败；SKIP 不计入 PASS。
  检查：`grep -n "skip_if\|SKIP" apitest/run_all.py`；报告 `apitest/report.html` 中 SKIP 行须写明原因。

## 缺陷判定口径

- 被当成成功：返回 2xx 但数据不落库、跨班可见、或 0 命中却调用了模型，都算缺陷。
  检查：`tests/test_assistant.py::TestConversationsAPI::test_sse_zero_hit_no_model_call`。
- 被放行：越权请求返回 2xx（学生写、跨班读、伪造 `class_id` 生效）都算缺陷。
  检查：`tests/test_role.py`、`tests/test_isolation.py`、`tests/test_retrieval.py::TestSearchClassIsolation`。
- 被误拒：合法请求返回 4xx/5xx（本班材料下载失败、已启用智能体建会话 404）算缺陷。
  检查：`tests/test_materials.py::TestDownload`、`tests/test_assistant.py::TestConversationsAPI::test_create_and_detail`。
- 未处理故障：依赖不可用时的表现与规范不符（该 503 却 500、该降级却阻断主路径、工具失败未进 `meta.tool_calls`）算缺陷。
  检查：`tests/test_retrieval.py::TestHybridAndRRF::test_qdrant_unavailable_hybrid_503`、`tests/test_mcp.py::TestToolLoop`。
