# 第 8 课安全检测清单（SEC-01 ~ SEC-07）

- 变更：`openspec/changes/2026-11-04-async-grading-tasks/`
- 日期：2026-11-04
- 环境：`docker compose`（web / api / db / qdrant / mcp-demo / worker），真实模型网关已配置
- 执行方式：容器内以 `http://web:80` 实测 + pytest 用例；可脚本化项见 `make check-security`

## 结论总表

| 编号 | 检查项 | 结论 | 证据 |
| --- | --- | --- | --- |
| SEC-01 | 未登录访问受保护接口 | 绿 | 未带令牌 `GET /api/assignments` → 401；`pytest tests/test_auth.py::TestAuthRequired` 通过 |
| SEC-02 | 跨班资源不可见 | 绿 | B 班学生提交 A 班作业 → 404；`pytest tests/test_isolation.py`、`tests/test_grading.py` 跨班用例通过 |
| SEC-03 | 学生不可改教师配置 | 绿 | 学生 `POST /api/assignments` → 403；`pytest tests/test_role.py::TestRoleRequired` 通过 |
| SEC-04 | 技能/工具不能绕过鉴权 | 绿 | 未连接服务器保存工具技能 → 400；模型提出未登记工具不计入结果；每问 3 轮/5 次上限用例通过 |
| SEC-05 | 仓库密钥扫描 | 绿 | 130 个文件，0 命中（`scripts/check_security.py`） |
| SEC-06 | 依赖漏洞基线 | **红** | `pip-audit` 未安装，无法产出 CVE 清单（本课保留红项） |
| SEC-07 | 审计日志七列 | 绿 | `audit_logs` 表七列（action / target_type / target_id / actor_id / class_id / skill_name / detail）+ `GET /api/audit-logs` 按班级查询；`pytest tests/test_audit.py` 13 个用例通过 |

## 逐项证据

### SEC-01 未登录

```text
SEC-01 unauth GET /api/assignments -> 401
```

### SEC-02 跨班

```text
SEC-02 B-class submit to A assignment -> 404
```

`404` 与「不存在资源」同构，响应体 `{"error": "not found"}`，不暗示资源存在。

### SEC-03 学生越权写配置

```text
SEC-03 student POST /api/assignments -> 403
```

### SEC-04 技能/工具绕过

- 技能保存四查（格式 / 已登记 / 已连接 / 在清单内）：未连接时 `POST /api/skills` → 400。
- 模型幻觉工具名不会出现在 `meta.tool_calls`，也不写审计成功行。
- 每问上限 3 轮、累计 5 次：`tests/test_mcp.py::TestToolLoop::test_round_and_total_caps` 通过。

### SEC-05 密钥扫描

```text
[PASS] SEC-05 密钥扫描: 扫描 130 个文件，未发现密钥字面量或非示例文件的密钥赋值
```

扫描范围排除 `.env`、`.env.example`、`reports/`、`uploads/` 与缓存目录。

### SEC-06 依赖漏洞基线（红）

```text
[RED] SEC-06 依赖漏洞基线: pip-audit 未安装（工具缺失，本课保留的红项）
```

补偿动作：`docker compose exec -T api pip check` → `No broken requirements found.`
补救项：在镜像中固定加入 `pip-audit`（或改用 CI 侧 SCA），下次课产出 CVE 表。

### SEC-07 审计日志七列（绿）

`audit_logs` 表七列落库，`GET /api/audit-logs` 按班级查询：

```sql
SELECT action, target_type, target_id, actor_id, class_id, skill_name, detail, created_at
FROM audit_logs WHERE class_id = 1 ORDER BY id DESC LIMIT 5;
```

```text
grade    | submission  | 18 | NULL | 1 | 作业批改  | {"jobId":18,"score":40,"ms":1820.4,"wrongQuestionId":3}
submit   | submission  | 18 | 3    | 1 | NULL      | {"assignmentId":1,"taskId":18}
explain  | wrong_question | 3 | 3  | 1 | 错题讲解  | {"conversationId":4,"agentId":1}
create   | assignment  | 1  | 1    | 1 | NULL      | {"title":"一元一次方程作业"}
login    | session     | NULL | 1  | 1 | NULL      | {"role":"teacher"}
```

字段对照（原红项要求）：

| 要求 | 落地位置 |
| --- | --- |
| 操作类型 | `action`（login/create/update/delete/download/submit/grade/explain/connect/disconnect/reindex） |
| 对象 | `target_type` + `target_id`（session/material/skill/agent/prompt/mcp_server/assignment/submission/wrong_question） |
| 技能标识 | `skill_name`（作业批改 / 错题讲解） |
| 用量与耗时 | `detail.ms`（批改耗时），`detail.score`，`detail.wrongQuestionId` |
| 谁在哪个班 | `actor_id` + `class_id`（worker 无人类操作者时为 NULL） |

查询接口：`GET /api/audit-logs?limit=50&action=grade&target_type=submission`（教师专用、班级隔离，未知过滤值 400）。
用例：`tests/test_audit.py`（13 个：七类写入 + 权限 + 跨班隔离 + 过滤 + 上限收敛）。

## 复现命令

```bash
docker compose exec -T api python scripts/check_security.py
docker compose exec -T api python -m pytest tests/test_auth.py tests/test_isolation.py tests/test_role.py tests/test_grading.py tests/test_mcp.py -q
docker compose logs --tail=12 worker
```

## 红项处理原则

本课要求「至少保留 1 条红」。SEC-06 作为已登记风险继续保留（`pip-audit` 未装），SEC-07 已在第 9 课转绿（见上方证据）。
