-- Lesson 5: assistant (prompt / skills / agents / conversations / messages).
-- MySQL 8.0 dialect, idempotent via IF NOT EXISTS.
--
-- class_prompts holds one system prompt per class. skills store both the
-- parsed fields and the raw source text (edit round-trips). agents bind
-- skills and materials through join tables. messages keep the SSE chat
-- transcript and assistant rows carry citations JSON + the applied skill name.

CREATE TABLE IF NOT EXISTS class_prompts (
    class_id   BIGINT PRIMARY KEY,
    body       TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_class_prompts_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS skills (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id    BIGINT NOT NULL,
    name        VARCHAR(128) NOT NULL,
    `trigger`   VARCHAR(255) NOT NULL DEFAULT '',
    tools       JSON NULL,
    subject     VARCHAR(128) NOT NULL DEFAULT '',
    description TEXT NOT NULL,
    source      MEDIUMTEXT NOT NULL,
    enabled     TINYINT(1) NOT NULL DEFAULT 1,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_skills_class (class_id, enabled),
    CONSTRAINT fk_skills_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agents (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id   BIGINT NOT NULL,
    name       VARCHAR(128) NOT NULL,
    prompt     TEXT NULL,
    enabled    TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_agents_class (class_id, enabled),
    CONSTRAINT fk_agents_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_skills (
    agent_id BIGINT NOT NULL,
    skill_id BIGINT NOT NULL,
    PRIMARY KEY (agent_id, skill_id),
    CONSTRAINT fk_agent_skills_agent FOREIGN KEY (agent_id)
        REFERENCES agents(id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_skills_skill FOREIGN KEY (skill_id)
        REFERENCES skills(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_materials (
    agent_id    BIGINT NOT NULL,
    material_id BIGINT NOT NULL,
    PRIMARY KEY (agent_id, material_id),
    CONSTRAINT fk_agent_materials_agent FOREIGN KEY (agent_id)
        REFERENCES agents(id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_materials_material FOREIGN KEY (material_id)
        REFERENCES materials(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS conversations (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    class_id   BIGINT NOT NULL,
    agent_id   BIGINT NOT NULL,
    title      VARCHAR(128) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_conversations_user (user_id, class_id),
    KEY idx_conversations_agent (agent_id),
    CONSTRAINT fk_conversations_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_conversations_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_conversations_agent FOREIGN KEY (agent_id)
        REFERENCES agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS messages (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    role            ENUM('user', 'assistant') NOT NULL,
    content         MEDIUMTEXT NOT NULL,
    citations       JSON NULL,
    skill_name      VARCHAR(128) NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_messages_conversation (conversation_id, id),
    CONSTRAINT fk_messages_conversation FOREIGN KEY (conversation_id)
        REFERENCES conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
