# AI 应用规范

适用范围：提示词、检索增强问答、智能体会话、MCP 工具调用。核心原则：有据才答，工具只做数据，密钥只在服务端。

## 调用边界

- 模型只经 `app/services/model_gateway.py` 在服务端调用（`embed_texts` / `chat` / `chat_with_tools` / `chat_stream`）；浏览器拿不到网关地址、密钥、模型名。
  检查：`grep -rn "EMBED_API_KEY\|CHAT_API_KEY" app/routes` 无匹配；`docker compose exec -T api python -m pytest -q tests/test_retrieval.py tests/test_assistant.py`。
- 网关未配置或不可达时降级而非崩溃：keyword 检索照常 200，vector/hybrid 与问答返回 503。
  检查：`tests/test_retrieval.py::TestKeywordSearch::test_keyword_works_when_qdrant_down`、`tests/test_retrieval.py::TestHybridAndRRF::test_qdrant_unavailable_hybrid_503`。
- 原始网关响应与异常原文不返回浏览器，只给短语；`detail` 仅 503 使用且取服务自身的短语。
  检查：`grep -rn "\"detail\"" app/routes` 除 schema 与审计字段外只在 `search.py`、`ask.py`、`api_conversations.py` 的 503 分支。
- 异步批改的 prompt 只含本题题目、参考答案与学生答案，不拼接材料切片、技能或 MCP 工具；批改调用与问答共用 `model_gateway.chat`，不新增直连。
  检查：`grep -n "knowledge\|skill\|mcp" app/services/grading.py` 无匹配；`tests/test_grading.py::TestWorker`。

## 工具只走既有服务层

- 内置工具只有 `knowledge_search`，它不对应外部调用，等同于每轮前置的班级混合检索（`retrieval.search`）；不做新的工具执行通道。
  检查：`grep -n "BUILTIN_TOOLS" app/services/mcp_service.py` 值为 `{"knowledge_search"}`。
- MCP 工具调用只经 `app/services/mcp_client.py`（initialize → tools/list → tools/call），单端点 JSON-RPC，Bearer 令牌来自 `mcp_servers.token`。
  检查：`grep -rn "jsonrpc" app/` 仅命中 `mcp_client.py`；`grep -rn "jsonrpc" mcp-server/` 命中服务端实现；`tests/test_mcp.py::TestMcpServerProtocol`。
- 每轮候选工具只取当轮技能实际引用且服务器已连接的清单（最小权限），不做全量暴露。
  检查：`app/services/mcp_service.py::build_candidates`；`tests/test_mcp.py::TestSkillReferenceValidation`。
- 工具参数按 `inputSchema` 校验后才发出，缺失必填即记 `denied`。
  检查：`app/services/chat.py::_schema_ok`；`tests/test_mcp.py::TestToolLoop::test_hallucinated_tool_not_attributed`。

## 提示词入库与版本

- 提示词一律入库、不硬编码在路由或前端：班级提示词 `class_prompts.body`（`PUT /api/prompt` 整体替换），技能引导正文 `skills.source`（含名称/适用条件/工具/资料/启用 + 空行后的正文）。
  检查：`grep -rn "class_prompts\|skills.source" app/repositories`；`tests/test_assistant.py::TestPromptAPI::test_teacher_put_then_get`。
- 智能体提示词与班级提示词不叠加：`agent.prompt` 非空时替代班级提示词，为空时回落到 `class_prompts.body`；技能段落与固定问答规则追加其后。
  检查：`grep -n "system_prompt = agent_prompt or class_prompt" app/services/chat.py`；`docker compose exec -T api python -m pytest tests/test_assistant.py::TestAgentsAPI -q` 通过。
- 提示词与技能没有独立版本号列：版本追溯以 git 提交与 openspec change 为准，变更必须在 proposal/design 里写明改前改后文本。
  检查：`git log -p -- app/services/answer.py app/services/chat.py`；`ls openspec/changes/archive` 有对应变更目录。
- 系统提示词的固定问答规则写在代码常量（`answer.GROUNDING_RULES`），改动即为行为变更，必须带用例。
  检查：`tests/test_retrieval.py::TestAsk::test_grounded_answer_with_citations`。

## 内置技能清单

- 四个并列技能均通过 `agent_skills` 与默认助手多对多绑定，seed 时全部 enabled=1：
  - **方程解题引导**（`seeds/seed.py::SEED_SKILL`）：数学学科，引导式回答，不给最终答案。
  - **作业批改**：由 worker 内部使用（`app/services/grading.py`），不是对话技能。
  - **错题讲解**（`seeds/seed.py::SEED_WRONG_QUESTION_SKILL`）：诊断错因（概念不清/计算失误/审题偏差/思路方向错误）→ 指出偏离步骤 → 分步提问引导，全程不直接给最终答案。由 `POST /api/wrong-questions/<id>/explain` 触发。
  - **关怀式对话**（`seeds/seed.py::SEED_CARE_SKILL`）：仅当学生消息命中挫败/焦虑词表（`app/services/chat.py::CARE_PATTERNS`）时注入，先共情再把目标缩小成一步；普通提问不注入。关怀轮次即使零命中也不走固定文案，仍调用模型作答。
- 新增/修改技能必须走 openspec change，且同步更新 seed + 测试。
  检查：`tests/test_wrong_questions.py::TestWrongQuestionSkillSeeded::test_skill_registered_and_bound`；`tests/test_care_skill.py::TestCareSkillSeeded::test_seeded_and_bound_in_both_classes`。

## 技能上传

- `POST /api/skills/import` 仅教师可用，接受 `.md` / `.json`，上限 64KB；工具引用复用四查，导入后一律 `enabled=0`，source 规整为单段文本（`启用：否`），教师确认后再编辑启用。
  检查：`tests/test_skill_import.py`（正常 md/json、415/413/400/409/403/401、停用→启用、跨班同名独立、审计字段）。

## 输出校验与不编造依据

- 0 命中返回固定文案「资料中未找到相关内容」+ 空 `citations`，且不调用模型。例外：解题助手（`/api/conversations/<id>/messages`）本轮技能引用了 MCP 工具时仍先跑工具循环，至少一次调用 ok 才基于工具数据调模型流式回答（citations 仍为空）；全部失败/被拒仍回固定文案且不调模型。`/ask` 无此例外。
  检查：`tests/test_retrieval.py::TestAsk::test_no_evidence_does_not_call_chat`、`tests/test_mcp.py::TestToolLoop::test_zero_hit_with_tool_call_streams_answer`、`tests/test_mcp.py::TestToolLoop::test_zero_hit_tool_error_keeps_fixed_message`。
- 有命中时 `citations` 顺序必须与 `[n]` 编号一致，从 1 起递增；出处必须指向本班切片。
  检查：`tests/test_retrieval.py::TestAsk::test_grounded_answer_with_citations`、`tests/test_assistant.py::TestConversationsAPI::test_agent_material_filter`。
- 问答取切片正文用 `excerpt_limit=2000`（不是检索展示的 200），保证依据完整。
  检查：`app/services/answer.py::build_answer` 的 `excerpt_limit=2000`。
- 历史只保留最近 6 条 user/assistant 轮次，`system` 与非法角色丢弃。
  检查：`app/services/answer.py::_sanitize_history`；`tests/test_retrieval.py::TestAsk::test_client_system_message_dropped`。

## 注入防护

- 工具返回一律按数据处理：拼进消息时放在"资料切片/data"段，绝不放进 system 段。
  检查：`app/services/chat.py::_data_segment`；`tests/test_mcp.py::TestReferenceAndSanitize::test_sanitize_tool_text`。
- 命中指令式句式（忽略/无视前文指令、你现在是、disregard previous、system prompt 等）整条丢弃，替换为固定提示「（该工具返回内容未通过安全检查，已忽略。）」，不做局部裁剪。
  检查：`app/services/mcp_service.py::INJECTION_PATTERNS`、`sanitize_tool_text`；`tests/test_mcp.py::TestReferenceAndSanitize::test_sanitize_tool_text`。
- 工具文本进入提示词前必须经 `sanitize_tool_text`，不得直接透传网关或前端原文。
  检查：`grep -n "sanitize_tool_text" app/services/chat.py` 出现在工具结果处理路径。
- 用户输入即使含指令式句式也照常当问题处理，但模型被"只用切片作答"规则约束；不额外做输入过滤以免误伤正常提问。
  检查：`tests/test_retrieval.py::TestAsk::test_grounded_answer_with_citations`。

## MCP 调用上限与失败处理

- 每问最多 3 轮工具提议、累计最多 5 次工具执行（`MCP_MAX_ROUNDS` / `MCP_MAX_CALLS`），达上限即停止调用并用已收集数据作答。
  检查：`tests/test_mcp.py::TestToolLoop::test_round_and_total_caps`。
- 服务器未连接、工具不在清单、参数不符均记 `denied` 审计行，不中断整轮回答。
  检查：`tests/test_mcp.py::TestToolLoop::test_denied_when_disconnected_between_prepare_and_call`。
- 模型提出不存在的工具时按"未提供"处理，不伪造调用结果、不写审计。
  检查：`tests/test_mcp.py::TestToolLoop::test_hallucinated_tool_not_attributed`。

## 评测与成本

- 拒答基线必须有：无命中不调模型、空问题 400、固定文案不漂移；扩充到 10–20 条评测题时随 openspec change 提交，不新建独立目录。
  检查：`docker compose exec -T api python -m pytest -q tests/test_retrieval.py tests/test_assistant.py`。
- 超时：网关连接 5s / 读 30s（`GATEWAY_TIMEOUT_CONNECT` / `GATEWAY_TIMEOUT_READ`），MCP 连接 3s / 读 15s（`MCP_TIMEOUT_CONNECT` / `MCP_TIMEOUT_READ`）。
  检查：`grep -n "GATEWAY_TIMEOUT_CONNECT\|GATEWAY_TIMEOUT_READ\|MCP_TIMEOUT_CONNECT\|MCP_TIMEOUT_READ" app/config.py` 默认值分别为 5/30 与 3/15。
- 成本边界由参数固定：`ASK_TOP_K=4`、单轮切片正文上限 2000 字、历史 6 条、工具 5 次、检索`final_limit=10`。
  检查：`grep -n "ASK_TOP_K\|EXCERPT_LIMIT\|SEARCH_FINAL_LIMIT" .env.example`。
- 流式回答在发出 `done` 前一次性落库；中途断开不写半截消息。
  检查：`app/services/chat.py::sse_stream`；`tests/test_assistant.py::TestConversationsAPI::test_sse_hit_flow`。
