-- Lesson 8: async grading (assignments / submissions / jobs).
-- MySQL 8.0 dialect, idempotent via IF NOT EXISTS.
--
-- jobs is the queue itself (no middleware): the worker claims one row with
-- `FOR UPDATE SKIP LOCKED`, marks it running, grades in the background and
-- writes the result back in the same transaction that closes the job.
-- submissions carries one row per (assignment, student) — the UNIQUE key is
-- what makes a repeated submit reuse the very same task and result.

CREATE TABLE IF NOT EXISTS assignments (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id         BIGINT NOT NULL,
    title            VARCHAR(128) NOT NULL,
    question         TEXT NOT NULL,
    reference_answer TEXT NOT NULL,
    created_by       BIGINT NOT NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_assignments_class (class_id, id),
    CONSTRAINT fk_assignments_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_assignments_creator FOREIGN KEY (created_by)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS submissions (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    assignment_id BIGINT NOT NULL,
    class_id      BIGINT NOT NULL,
    student_id    BIGINT NOT NULL,
    answer        MEDIUMTEXT NOT NULL,
    status        ENUM('pending', 'running', 'succeeded', 'failed') NOT NULL
        DEFAULT 'pending',
    score         SMALLINT NULL,
    feedback      MEDIUMTEXT NULL,
    graded_at     DATETIME NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_submissions_assignment_student (assignment_id, student_id),
    KEY idx_submissions_class (class_id, id),
    CONSTRAINT fk_submissions_assignment FOREIGN KEY (assignment_id)
        REFERENCES assignments(id) ON DELETE CASCADE,
    CONSTRAINT fk_submissions_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_submissions_student FOREIGN KEY (student_id)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- dedupe_key makes enqueue idempotent (grade:<submission_id>) and the UNIQUE
-- index is the second line of defence when two requests race.
CREATE TABLE IF NOT EXISTS jobs (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id     BIGINT NOT NULL,
    kind         VARCHAR(32) NOT NULL,
    dedupe_key   VARCHAR(128) NOT NULL,
    payload      JSON NULL,
    status       ENUM('pending', 'running', 'succeeded', 'failed') NOT NULL
        DEFAULT 'pending',
    attempts     INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    last_error   VARCHAR(255) NULL,
    locked_at    DATETIME NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_jobs_dedupe (dedupe_key),
    KEY idx_jobs_status (status, id),
    KEY idx_jobs_class (class_id),
    CONSTRAINT fk_jobs_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
