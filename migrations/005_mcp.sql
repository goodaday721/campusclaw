-- Lesson 6: MCP tool integration (registry, discovery cache, call audit).
-- MySQL 8.0 dialect, idempotent via IF NOT EXISTS.
--
-- mcp_servers registers one tool server per class row (name unique per
-- class). The Bearer token column stays server-side only — API responses
-- expose a hasToken boolean, never the raw token. mcp_tools_cache holds the
-- latest SUCCESSFUL tools/list discovery result (replaced wholesale on every
-- connect, emptied on disconnect/failure). mcp_call_logs is one row per
-- attributable tool invocation (ok/denied/error) with user/conversation/round
-- for the five audit questions.

CREATE TABLE IF NOT EXISTS mcp_servers (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id   BIGINT NOT NULL,
    name       VARCHAR(128) NOT NULL,
    base_url   VARCHAR(500) NOT NULL,
    token      VARCHAR(500) NULL,
    status     ENUM('disconnected', 'connected') NOT NULL DEFAULT 'disconnected',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_mcp_servers_class_name (class_id, name),
    CONSTRAINT fk_mcp_servers_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS mcp_tools_cache (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    server_id   BIGINT NOT NULL,
    name        VARCHAR(128) NOT NULL,
    description TEXT NULL,
    input_schema JSON NULL,
    UNIQUE KEY uq_mcp_tools_server_name (server_id, name),
    CONSTRAINT fk_mcp_tools_server FOREIGN KEY (server_id)
        REFERENCES mcp_servers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS mcp_call_logs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    class_id        BIGINT NOT NULL,
    server_id       BIGINT NULL,
    server_name     VARCHAR(128) NOT NULL,
    tool_name       VARCHAR(128) NOT NULL,
    status          ENUM('ok', 'denied', 'error') NOT NULL,
    detail          VARCHAR(500) NULL,
    user_id         BIGINT NOT NULL,
    conversation_id BIGINT NOT NULL,
    round_no        INT NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_mcp_logs_class_time (class_id, created_at),
    CONSTRAINT fk_mcp_logs_server FOREIGN KEY (server_id)
        REFERENCES mcp_servers(id) ON DELETE SET NULL,
    CONSTRAINT fk_mcp_logs_class FOREIGN KEY (class_id)
        REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_mcp_logs_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_mcp_logs_conversation FOREIGN KEY (conversation_id)
        REFERENCES conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
