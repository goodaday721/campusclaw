# 设计：错题本与错题讲解技能

## 数据模型

```sql
CREATE TABLE wrong_questions (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id         BIGINT NOT NULL,
    submission_id    BIGINT NOT NULL,
    student_id       BIGINT NOT NULL,
    question         TEXT NOT NULL,            -- 从 assignment 冗余过来
    student_answer   MEDIUMTEXT NOT NULL,      -- 从 submission 冗余
    reference_answer TEXT NOT NULL,            -- 从 assignment 冗余
    reason           VARCHAR(255) NOT NULL,    -- 截取的 feedback 前 200 字
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_wrong_questions_submission (submission_id),
    KEY idx_wrong_questions_class (class_id, id),
    KEY idx_wrong_questions_student (student_id, class_id),
    CONSTRAINT fk_wq_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_wq_submission FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE,
    CONSTRAINT fk_wq_student FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**关键决策**：
- `UNIQUE(submission_id)` 让 worker 重放/重试时只产生一条错题，幂等由数据库约束兜底。
- `question / student_answer / reference_answer` 做**冗余**而非 JOIN：错题本要快查，且作业原题即使后来改也不会影响历史错题。
- `reason` 直接截 feedback 前 200 字，不另起模型调用做"错因分类"——本课不引入额外网关开销。

## 写入时机

worker `_succeed()` 内：

```python
repo.finish_submission(conn, submission_id, score, feedback, "succeeded")
if score is not None and score < 60:
    wrong_questions_repo.upsert_from_submission(conn, submission_id, class_id)
repo.finish_job(conn, job["id"], "succeeded")
conn.commit()  # 同一事务
```

`upsert_from_submission` 内部 JOIN submissions + assignments 拿题目/答案/学生答案，一次性 INSERT ... ON DUPLICATE KEY UPDATE。

**阈值选择**：`score < 60` 作为"判错"的判定线，与常见及格线一致。阈值硬编码，不做配置项（Non-Goal）。

## 讲解对话链路

`POST /api/wrong-questions/<id>/explain` 内部流程：

1. 鉴权 + 班级作用域查到该错题。
2. 查该生（或教师代查）所在的班级默认解题助手（`agents` 里 enabled=1 的第一条）。
3. 创建一条 `conversations` 行：`title = f"错题讲解 #{id}"`。
4. 把错题的 `question / student_answer / reference_answer / reason` 作为**用户消息**塞进 `messages`。
5. 调 `chat_service.stream_chat(conversation_id, ...)` 复用现有 SSE 管线；技能选择走默认绑定（错题讲解技能已在 seed 里绑到默认助手）。
6. 返回 SSE 流，前端用现有对话渲染组件。

**为什么不新开技能路由**：错题讲解只是「带特定初始用户消息的对话」，复用 chat 链路最自然，不引入第二条 SSE 通道。

## 技能 system_prompt

```
名称：错题讲解
适用条件：学生请求讲解一道已判错的题
工具：knowledge_search
启用：是

你是"错题讲解"技能。面对一道判错的题，你必须：
1. 先诊断错因类型：概念不清 / 计算失误 / 审题偏差 / 思路方向错误，用一句话点明；
2. 指出学生答案里**具体哪一步**开始偏离；
3. 用提问方式引导学生自己发现正确路径（每次只问一个引导问题）；
4. 学生给出新思路后再确认或继续引导；
5. 全程不直接给最终答案；学生推出正确答案后再让其对照参考答案验证。
```

## 权限矩阵

| 操作 | 学生（本人） | 学生（他人） | 教师（本班） | 跨班 |
|---|---|---|---|---|
| GET /api/wrong-questions | 只见自己 | - | 见本班全部 | 空列表 |
| GET /api/wrong-questions/&lt;id&gt; | 200 | 404 | 200 | 404 |
| POST /api/wrong-questions/&lt;id&gt;/explain | 200 SSE | 404 | 200 SSE | 404 |

教师可以代替学生触发讲解（用于课堂演示）；学生只能触发自己的。

## 测试策略

- `TestWrongQuestionGeneration`：低分写入 / 高分不写 / 重放不重复
- `TestWrongQuestionIsolation`：跨班列表为空 / 跨班详情 404 / 学生查他人 404
- `TestWrongQuestionExplain`：学生触发自己的 → SSE 200 / 学生触发他人的 → 404 / 教师触发本班 → SSE 200
- `TestWrongQuestionSkillSeeded`：seed 后 A/B 两班各有「错题讲解」技能且 enabled=1，绑定到默认助手
