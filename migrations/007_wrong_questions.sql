-- Wrong questions (lesson 11 必做): one row per failed submission.
-- UNIQUE(submission_id) makes worker replays idempotent. question/answers are
-- denormalized from assignments + submissions so the wrong-question list is a
-- single-table lookup and history is preserved even if the assignment changes.

CREATE TABLE IF NOT EXISTS wrong_questions (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id         BIGINT NOT NULL,
    submission_id    BIGINT NOT NULL,
    student_id       BIGINT NOT NULL,
    question         TEXT NOT NULL,
    student_answer   MEDIUMTEXT NOT NULL,
    reference_answer TEXT NOT NULL,
    reason           VARCHAR(255) NOT NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_wrong_questions_submission (submission_id),
    KEY idx_wrong_questions_class (class_id, id),
    KEY idx_wrong_questions_student (student_id, class_id),
    CONSTRAINT fk_wq_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_wq_submission FOREIGN KEY (submission_id)
        REFERENCES submissions(id) ON DELETE CASCADE,
    CONSTRAINT fk_wq_student FOREIGN KEY (student_id)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
