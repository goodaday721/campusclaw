-- Sessions and knowledge_entries for add-session-auth-knowledge-ingest
-- (MySQL 8.0 dialect, idempotent via IF NOT EXISTS + inline indexes).

CREATE TABLE IF NOT EXISTS sessions (
    id         VARCHAR(128) PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    expires_at DATETIME NOT NULL,
    KEY idx_sessions_user_id (user_id),
    KEY idx_sessions_expires_at (expires_at),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_entries (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    material_id BIGINT NOT NULL,
    class_id    BIGINT NOT NULL,
    content     TEXT NOT NULL,
    source      VARCHAR(255) NOT NULL,
    KEY idx_knowledge_material_id (material_id),
    KEY idx_knowledge_class_id (class_id),
    CONSTRAINT fk_knowledge_material FOREIGN KEY (material_id)
        REFERENCES materials(id) ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_class FOREIGN KEY (class_id) REFERENCES classes(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
