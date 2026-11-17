# 设计：审计日志

## 数据模型（七列）

```sql
CREATE TABLE audit_logs (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id    BIGINT NOT NULL,        -- 1 哪个班
    actor_id    BIGINT NULL,            -- 2 谁（worker 为 NULL）
    action      VARCHAR(32) NOT NULL,   -- 3 操作类型
    target_type VARCHAR(32) NOT NULL,   -- 4 对象类型
    target_id   BIGINT NULL,            -- 5 对象 id
    skill_name  VARCHAR(128) NULL,      -- 6 技能标识
    detail      JSON NULL,              -- 7 用量与耗时等
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

`actor_id` 可空：worker 批改没有人类操作者，`detail.studentId`/`jobId` 仍可追责。

## 写入时机与事务边界

| 操作 | action | target_type | skill_name | 事务 |
|---|---|---|---|---|
| 登录 / 登出 | login / logout | session | - | 独立事务 |
| 上传材料 | create | material | - | 上传已提交后独立写 |
| 重建索引 | reindex | material | - | 索引完成后独立写 |
| 下载材料 | download | material | - | 授权通过后独立写 |
| 技能增改删 | create/update/delete | skill | 技能名 | 业务提交后独立写 |
| 智能体增改 | create/update | agent | - | 业务提交后独立写 |
| 提示词更新 | update | prompt | - | 业务提交后独立写 |
| MCP 登记/更新/删除 | create/update/delete | mcp_server | - | 业务提交后独立写 |
| MCP 连接/断开 | connect / disconnect | mcp_server | - | 业务提交后独立写（失败也记） |
| 作业创建 | create | assignment | - | 业务提交后独立写 |
| 学生提交 | submit | submission | - | 业务提交后独立写 |
| 批改完成 | grade | submission | 作业批改 | **与结果同事务** |
| 错题讲解 | explain | wrong_question | 错题讲解 | 会话创建后独立写 |

**为什么批改要同事务**：批改结果与审计行是同一次状态跃迁，若结果写入而审计丢失，事后无法证明「这次分数是谁在什么时刻给的」。其余操作采用 best-effort：审计写失败只打一行 `audit_write_failed` 日志，绝不把成功的业务变成 500。

## 查询接口

`GET /api/audit-logs?limit=50&action=grade&target_type=submission`

- `@auth_required` + `@role_required("teacher")`
- 只查 `class_id = 当前用户班级`
- `limit` clamp 到 1..200
- `action` / `target_type` 只接受白名单值，未知值 400（避免拼进 SQL 的任意串）

## 为什么不用 stdout 日志承载七列

容器日志不可按班级查询，也无法在答辩现场用接口演示「谁在什么时候改了哪个技能」。数据库行 + 查询接口同时满足「可追溯」与「可演示」；stdout 仍保留一行 JSON 用于排障，两者职责分离。

## 测试策略

- `TestAuditWrites`：登录 / 登出 / 上传 / 作业 / 提交 / 批改 / 讲解七条写入
- `TestAuditAPI`：教师可读本班、学生 403、未登录 401、跨班隔离、action 过滤、未知过滤 400、limit 收敛
