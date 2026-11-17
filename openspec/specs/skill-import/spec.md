# skill-import Specification

## Purpose
技能包上传能力：教师通过 `POST /api/skills/import` 上传 `.md` 或 `.json` 技能文件（≤64KB），服务端解析并复用工具引用四查，导入后一律停用、source 规整为可在编辑框继续编辑的单段文本，教师确认后再启用；全程写入审计。

## Requirements

### Requirement: 技能包上传

系统 SHALL 提供 `POST /api/skills/import`，仅教师可调用；接受 multipart 字段 `file`，支持 `.md` 与 `.json` 两种格式，单文件上限 64KB；导入的技能 MUST 以停用状态（`enabled=0`）落库，且 `source` MUST 被规整为可在编辑框继续编辑的单段文本。

#### Scenario: 导入 md 技能包

- **WHEN** 教师上传含 `名称/适用条件/资料/启用` 与正文的 `.md` 文件
- **THEN** 返回 201，技能 `enabled=false`，source 含 `启用：否` 与正文

#### Scenario: 导入 json 技能包

- **WHEN** 教师上传 `{"name":"JSON技能","description":"正文"}` 或 `{"source":"<整段 source>"}`
- **THEN** 返回 201，字段按 JSON 解析，`enabled=false`

#### Scenario: 扩展名不在白名单

- **WHEN** 上传 `.py` 或无扩展名文件
- **THEN** 返回 415

#### Scenario: 文件超限

- **WHEN** 上传超过 64KB 的文件
- **THEN** 返回 413，不写库

#### Scenario: 内容不可解析

- **WHEN** 上传非 UTF-8 文件，或缺少名称/正文的 md，或非法 JSON
- **THEN** 返回 400 与可读错误

#### Scenario: 同名技能冲突

- **WHEN** 本班已存在同名技能时再次导入
- **THEN** 返回 409；不同班级可各自存在同名技能

#### Scenario: 工具引用未登记

- **WHEN** 导入文件里的 `工具：` 行引用未登记/未连接的工具
- **THEN** 返回 400，不写库

#### Scenario: 学生越权

- **WHEN** 学生调用导入接口
- **THEN** 返回 403；未登录返回 401

#### Scenario: 导入后可启用

- **WHEN** 教师把导入技能的 source 改为 `启用：是` 并 PUT 更新
- **THEN** 技能 `enabled=true`，学生随后能在技能列表看到它

#### Scenario: 导入被审计

- **WHEN** 导入成功
- **THEN** `audit_logs` 新增 `action=create, target_type=skill`，`detail.import=true` 且含原始文件名
