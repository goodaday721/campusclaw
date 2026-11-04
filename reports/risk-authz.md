# 风险清单：鉴权与越权（risk-authz）

范围：第 8 课新增的作业/提交/批改链路，及既有班级隔离边界。

| 风险 | 触发方式 | 现状 | 结论 |
| --- | --- | --- | --- |
| 未登录读取作业 | 无 Bearer 调 `/api/assignments` | `@auth_required`，返回 401 | 已覆盖 |
| 学生创建作业 | 学生调 `POST /api/assignments` | `@role_required("teacher")`，403 | 已覆盖 |
| 教师代学生提交 | 教师调提交端点 | 显式 `role != student` → 403 | 已覆盖 |
| 跨班读取作业/提交 | B 班用户猜 A 班 id | 所有读取带 `class_id`；跨班与不存在同构 404 | 已覆盖 |
| 学生读取他人提交 | 改 URL 中的提交 id | `student_id` 归属校验，非本人 404 | 已覆盖 |
| 提交载荷伪造班级 | body 里塞 `class_id` | 服务端只取会话班级，body 字段被忽略 | 已覆盖 |
| 任务载荷泄露 | 直接查 `jobs` 表 | `jobs` 不映射宿主机端口，仅 api/worker 内网可见 | 已覆盖 |
| 返回令牌/密钥 | 作业接口响应 | 响应不含 `token`，MCP 仍只返回 `hasToken` | 已覆盖 |
| 教师看本班提交 | 教师查提交 id | 设计允许（教学需要），仅限 `class_id` | 接受 |
| 权限变更即时性 | 用户改班/降权 | 每请求从 `users` 表读取角色与班级 | 已覆盖 |

## 实测

```text
SEC-01 unauth GET /api/assignments -> 401
SEC-03 student POST /api/assignments -> 403
SEC-02 B-class submit to A assignment -> 404
```

对应用例：

- `tests/test_grading.py::TestAssignmentsAPI::test_student_cannot_create`
- `tests/test_grading.py::TestSubmissionsAPI::test_cross_class_submit_isomorphic_404`
- `tests/test_grading.py::TestPollingAPI::test_other_student_404`
- `tests/test_grading.py::TestPollingAPI::test_cross_class_teacher_404`

## 残余风险

1. 教师可查看本班全部提交，属于教学场景的显式设计；未做「仅看自己布置的作业」细分。
2. 作业删除依赖数据库级联（`ON DELETE CASCADE`），当前没有删除作业的接口，风险不可达。
3. 提交内容无长度上限（仅受 MySQL `MEDIUMTEXT` 限制）；后续如需防滥用，应在服务层加字符数上限。
