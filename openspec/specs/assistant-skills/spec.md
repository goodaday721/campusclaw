# assistant-skills Specification

## Purpose
内置技能注册与绑定：定义系统随 seed 写入的内置技能（方程解题引导、错题讲解）的 source 格式、enabled 默认值与 `agent_skills` 绑定关系；教师可在技能管理页对任一技能启停，停用后默认助手的对话不再注入该技能段落。

## Requirements

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

### Requirement: 关怀式对话的条件注入

系统 SHALL 内置「关怀式对话」技能并默认启用、绑定到本班默认助手；该技能 MUST 仅在学生消息命中挫败/焦虑词表时注入系统提示，普通提问 MUST NOT 注入；技能被停用后 MUST NOT 注入。

#### Scenario: seed 后技能存在且绑定

- **WHEN** 执行 seed
- **THEN** A/B 两班各有 1 行 `name='关怀式对话'`、`enabled=1`，且至少绑定 1 个 agent

#### Scenario: 挫败消息注入关怀

- **WHEN** 学生发送「这道题我完全不会，好难，有点想放弃了」
- **THEN** 模型收到的 system 消息含 `【技能：关怀式对话】`，同时仍含解题引导与错题讲解

#### Scenario: 普通提问不注入关怀

- **WHEN** 学生发送「什么是方程」
- **THEN** system 消息不含 `【技能：关怀式对话】`

#### Scenario: 技能停用后不再注入

- **WHEN** 教师将「关怀式对话」置为停用后再发挫败消息
- **THEN** system 消息不含该技能段落

### Requirement: 关怀轮次不受零命中文案短路

系统 SHALL 在关怀轮次即使检索零命中、无工具结果时仍调用模型作答，而不是返回「资料中未找到相关内容」固定文案；普通轮次的零命中短路行为 MUST 保持不变。

#### Scenario: 零命中但情绪挫败

- **WHEN** 本班没有任何材料，学生发送挫败消息
- **THEN** 调用模型并流式返回回答，citations 为空

#### Scenario: 零命中的普通提问

- **WHEN** 本班没有任何材料，学生发送普通提问
- **THEN** 不调用模型，返回固定文案
