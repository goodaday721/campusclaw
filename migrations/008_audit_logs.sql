-- Lesson 9/11: queryable audit records (SEC-07).
-- One row per auditable operation, seven business columns:
--   action(操作类型) / target_type(对象) / target_id / actor_id / class_id
--   skill_name(技能标识) / detail(用量与耗时等 JSON)
-- Reads are always class-scoped so teachers only see their own class.

CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id    BIGINT NOT NULL,
    actor_id    BIGINT NULL,
    action      VARCHAR(32) NOT NULL,
    target_type VARCHAR(32) NOT NULL,
    target_id   BIGINT NULL,
    skill_name  VARCHAR(128) NULL,
    detail      JSON NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_audit_class_time (class_id, created_at),
    KEY idx_audit_action (class_id, action),
    CONSTRAINT fk_audit_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_audit_actor FOREIGN KEY (actor_id)
        REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
