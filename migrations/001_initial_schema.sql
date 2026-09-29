-- Initial schema for add-auth-class-isolation (MySQL 8.0 dialect).
-- Indexes are declared inline (MySQL has no CREATE INDEX IF NOT EXISTS),
-- so re-running the whole script is idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS classes (
    id    BIGINT AUTO_INCREMENT PRIMARY KEY,
    name  VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS users (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          ENUM('teacher', 'student') NOT NULL,
    class_id      BIGINT NOT NULL,
    KEY idx_users_class_id (class_id),
    CONSTRAINT fk_users_class FOREIGN KEY (class_id) REFERENCES classes(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS materials (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id         BIGINT NOT NULL,
    uploader_user_id BIGINT NOT NULL,
    filename         VARCHAR(255) NOT NULL,
    storage_key      VARCHAR(255) NOT NULL,
    mime             VARCHAR(255) NOT NULL,
    size             BIGINT NOT NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_materials_class_id (class_id),
    CONSTRAINT fk_materials_class FOREIGN KEY (class_id) REFERENCES classes(id),
    CONSTRAINT fk_materials_uploader FOREIGN KEY (uploader_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
