# 设计：zero-hit-tool-loop

## 现状与根因

`chat.py::start` 在 `_prepare` 后立即按 `prepared["no_match"]` 短路返回 `gen=None`，而候选集构建与工具循环（`build_candidates` + `_run_tool_loop`）位于短路之后；`sse_stream` 同样按 `no_match` 输出固定话术。于是「10千克等于多少克」这类检索不命中的问题永远到不了工具声明那一步。

## 关键决策

1. **收窄短路条件，不复制第二套循环**。`start` 仅当「零命中 且 本轮无有效技能引用（`skill_refs` 为空）」时短路；`skill_refs` 非空时复用既有消息构建、候选集与循环代码路径。`build_sources_message(content, hits=[])` 在零命中时产出「无切片、只有问题」的用户消息，天然可用，无需新分支。
2. **成功判据沿用「任一 meta status == ok」**。与 hit 路径追加 TOOL_DATA_NOTE 的既有约定一致：只有存在 ok 的工具数据才值得调模型；全部 denied/error/无调用则维持固定话术。防编造原则不变——无任何依据（切片与工具数据皆无）不调模型。
3. **`sse_stream` 改按 `gen is None` 分流**。gen 为 None 的唯一来源是「零命中且无 ok 工具数据」，此时 meta 事件先发（可能携带 denied/error 的 tool_calls，如实披露尝试过程），随后固定话术 delta 与 done；零命中+工具成功走既有流式路径，citations 天然为空、assistant 消息照常落库。
4. **无引用的零命中路径零开销**。技能未引用 MCP 工具时 `skill_refs` 为空，立即短路，不多发任何网关调用，现有 `test_sse_zero_hit_no_model_call`（朴素智能体）与 `test_agent_material_filter` 语义不变。
5. **失败也可见**。零命中+工具全失败时 meta.tool_calls 携带 denied/error 记录后再回固定话术，与 hit 路径的 TOCTOU 披露策略一致，不静默吞掉尝试。
6. **工具参数容错（实测补充）**。真实环境实测发现：模型按 inputSchema 描述里的示例（`如 千米/km`）传了 `千克/kg`、`克/g` 这类复合单位，`unit_convert` 原实现只认裸单位 → 返回「换算失败：暂不支持…」文本（isError=false，宿主按 status=ok 审计），模型拿到失败文本后按 grounding 规则拒答。修法：单位匹配先整串、再按 `/` 拆分任取一侧；schema 示例格式从此成为合法输入。该修复不改变 tools/list 契约与 spec 文本。
7. **命中无关切片时工具数据优先（实测补充）**。第二个实测失败场景：检索对纯换算问题也会命中文档（如仅收录方程知识点的材料），此时不是零命中，走的是有命中链路——模型看到切片与本问题无关，即使工具已返回 ok 的换算结果，仍按 `GROUNDING_RULES` 回「资料中未找到相关内容」。修法：把 `TOOL_DATA_NOTE` 从「可引用」升级为强制优先级——工具数据已含答案时必须据此作答、禁止回固定拒答话术、不得因切片无关而拒答；该说明仍只追加在 system 段末尾，工具返回文本本身仍只在用户消息的数据段。检索相关性门控不在本次范围。

## 风险与取舍

- `GROUNDING_RULES` 仍写「只能依据资料切片」：由追加在 system 段末尾的 `TOOL_DATA_NOTE` 显式覆盖——工具数据优先级更高、含答案时必须据此作答且禁止回固定拒答话术。不改共享规则常量（改常量即行为变更且波及 `/ask`）。
- 提示词注入面不变：工具文本仍经 `sanitize_tool_text`、仍以数据段进用户消息，不进系统提示。
- 零命中时用户消息只有「问题」无切片，模型可能试图泛泛而谈：TOOL_DATA_NOTE + GROUNDING_RULES 双重约束下，无 ok 数据的路径根本不会调模型，有 ok 数据时依据明确。
