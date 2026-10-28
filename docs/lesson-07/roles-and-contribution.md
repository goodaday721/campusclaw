# 第 7 课 · 角色分工与个人贡献记录

## 组队情况

小组人数：1 人。按课程要求「不足 3 人时须兼任」，本人兼任全部三个角色，并在下文逐角色写明产出与证据。

## 角色一 · 制定规约（兼任）

- 产出：`openspec/specs/` 11 个能力主 spec、133 条 Scenario；三个历史变更的 proposal / design / tasks / specs 四份文件。
- 每条能力至少一组 Scenario，失败路径覆盖参数非法、无权限、资源不存在、依赖不可达四类；`openspec validate --all --strict` 11/11 通过。
- 证据：`docs/lesson-07/ability-scenarios.md`（能力 ↔ Scenario 对照表）、`docs/lesson-07/verification.md`（校验输出）。

## 角色二 · 开发系统（兼任）

- 产出：Flask + MySQL 8.0 + Qdrant + Nginx 五服务系统；第 1–6 课能力（认证授权、班级隔离、知识库入库与三路检索、提示词/技能/智能体与 SSE 流式回答、MCP 工具登记与调用审计）。
- 本次第 7 课增量：`/health/ready` 依赖探活、单行 JSON 访问日志与 `X-Request-Id` 回显、8 份工程规范、变更归档与骨架标签。
- 证据：提交历史（每条提交写明改了什么与依据）、`tests/` 134 例、`apitest/` 25 例、`e2e_test.py` 71 项。

## 角色三 · 项目验收（兼任）

- 验收方式：只按规约判定，不接受「模型声称完成」；逐条对照第 7 课核查清单（仓库 / 规约 / 规范 / 骨架 / 交付五维）。
- 交叉评审：本人在独立目录重新 clone、复制本地 `.env` 并改端口，用一条命令从零拉起五服务，确认不依赖「只在某人机器上能跑」的状态；结果记入 `verification.md` 的「交叉评审」节。
- 证据：`verification.md` 中的命令与真实输出、`openspec validate` 输出、门禁三条命令的通过计数。

## 个人贡献记录（按课程要求填写）

| 维度 | 本人承担 | 可核对证据 |
| --- | --- | --- |
| 规约 | 全部 11 个能力 spec 与 133 条 Scenario、四份变更文件 | `openspec/specs/`、`openspec/changes/archive/` |
| 开发 | 全部后端、前端页面、`mcp-server/`、迁移、种子、测试 | `app/`、`migrations/`、`mcp-server/`、`seeds/` |
| 规范 | `AGENTS.md` 与 8 份规范明细 | `AGENTS.md`、`docs/standards/` |
| 验收 | 核查清单逐条、交叉评审、门禁执行 | `docs/lesson-07/verification.md` |
| 交付 | 仓库、标签、README、验证记录 | GitHub 仓库地址、`v0.0.1-skeleton` 标签 |

说明：因 1 人独立完成，不存在组内分工争议；若后续扩组，按课程三角色直接接管对应目录即可。
