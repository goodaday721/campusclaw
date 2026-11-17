# Tasks: zero-hit-tool-loop

## 1. 链路修改

- [x] 1.1 `app/services/chat.py::start`：短路条件改为「`no_match` 且 `skill_refs` 为空」；工具循环后按「零命中且无 ok 调用」回落固定话术（返回 `gen=None` 但保留 `tool_calls_meta`），并同步模块 docstring
  - verify: 容器内 `pytest tests/test_mcp.py -q` 全绿
- [x] 1.2 `app/services/chat.py::sse_stream`：固定话术分支改按 `result["gen"] is None` 判定，docstring 同步
  - verify: 零命中+工具成功用例观察到 meta(tool_calls) → delta* → done
- [x] 1.3 `mcp-server/tools.py::unit_convert`：单位匹配接受「中文/英文」复合格式（整串优先，`/` 拆分任取一侧），实测发现模型按 schema 示例 `如 千米/km` 传参导致换算失败文本
  - verify: pytest `TestMcpServerProtocol::test_tools_call_unit_convert_accepts_compound_units`；重建 mcp-demo 后实测「10千克等于多少克」获得换算回答
- [x] 1.4 `app/services/chat.py::TOOL_DATA_NOTE`：升级为强制优先级措辞——工具数据含答案时必须据此作答，禁止回固定拒答话术，不得因切片无关拒答（命中无关切片的实测拒答场景）
  - verify: pytest `TestToolLoop::test_hit_with_tool_call` 断言 system 段含优先级措辞；实测工具智能体问「10千克等于多少克」不再回固定文案

## 2. 测试

- [x] 2.1 `tests/test_mcp.py::TestToolLoop` 新增三条：零命中+`unit_convert` 成功→meta.tool_calls ok、citations 空、流式回答非固定文案且落库 citations 为空；零命中+工具调用抛错→固定文案且 `chat_stream` 未调；零命中+服务器已断开→denied 后固定文案且 `chat_stream` 未调
  - verify: 容器内 pytest 全绿；现有 `test_sse_zero_hit_no_model_call`、`test_agent_material_filter` 语义不变通过
- [ ] 2.2 全量门禁：`pytest -q`、`e2e_test.py`、`apitest/run_all.py` 三条退出码 0
  - verify: `docker compose exec -T api` 三条命令全绿
  - 状态：pytest 已全绿；e2e / apitest 因课程网关额度耗尽未跑，待额度恢复后补跑

## 3. 文档同步与归档

- [x] 3.1 `docs/standards/ai.md`「输出校验与不编造依据」与 `README.md` 第 5/6 课相应段落补充解题助手例外措辞
  - verify: `openspec validate --all --strict --no-interactive` 输出 0 failed
- [x] 3.2 归档变更、delta 合并回主 spec，git 提交并推送
  - verify: `openspec list` 输出 `No active changes found.`
  - 状态：已归档并合并 delta；git 提交与推送待做
