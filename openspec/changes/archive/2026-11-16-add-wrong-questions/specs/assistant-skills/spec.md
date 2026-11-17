## ADDED Requirements

### Requirement: 错题讲解技能注册

系统 SHALL 在 seed 时向 A/B 两班的 `skills` 表各插入一行 `name='错题讲解'`、`enabled=1` 的技能记录，并通过 `agent_skills` 绑定到本班默认解题助手；技能 source MUST 包含完整 frontmatter（名称/适用条件/工具/资料/启用）与正文 prompt，正文 MUST 要求先诊断错因再分步引导、不直接给最终答案。

#### Scenario: seed 后技能存在且启用

- **WHEN** 执行 `seeds/seed.py` 完成种子
- **THEN** A 班和 B 班各有 1 行 `name='错题讲解'`、`enabled=1`，且每行至少绑定到 1 个 agent

#### Scenario: seed 重跑幂等

- **WHEN** 重复执行 seed
- **THEN** 技能行数不变（按 (class_id, name) 判重）

#### Scenario: 讲解对话激活技能

- **WHEN** 学生通过 `POST /api/wrong-questions/<id>/explain` 触发讲解
- **THEN** SSE 流中的模型回答风格符合技能 prompt：先点明错因类型，再分步引导，全程不直接给最终答案

### Requirement: 默认助手技能绑定清单

系统 SHALL 让本班默认解题助手至少绑定「方程解题引导」与「错题讲解」两个 enabled=1 的技能；两者通过 `agent_skills` 多对多绑定，教师 MUST 能在技能管理页对任一技能启停。

#### Scenario: 默认助手绑多技能

- **WHEN** 查询本班默认解题助手的绑定列表
- **THEN** 至少包含「方程解题引导」与「错题讲解」两个技能，均 enabled=1
