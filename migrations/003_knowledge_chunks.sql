-- Lesson 4: knowledge chunks + ngram fulltext index (idempotent MySQL 8.0).
--
-- Chunk text lives ONLY here (MySQL). The vector store (Qdrant) holds vectors
-- keyed by knowledge_chunks.id plus identifier payload, never the text itself.
-- ngram_token_size defaults to 2 in MySQL 8.0, which matches the course spec.
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    material_id BIGINT NOT NULL,
    knowledge_entry_id BIGINT NOT NULL,
    class_id BIGINT NOT NULL,
    chunk_index INT NOT NULL,
    chunk_text MEDIUMTEXT NOT NULL,
    char_start INT NOT NULL,
    char_end INT NOT NULL,
    strategy VARCHAR(16) NOT NULL DEFAULT 'auto',
    -- index_status: chunk TEXT readiness for keyword FULLTEXT, independent of
    -- embedding success and ready once the row is written.
    index_status ENUM('ready', 'failed') NOT NULL DEFAULT 'ready',
    -- embedding_status tracks vector index state in Qdrant.
    embedding_status ENUM('pending', 'ready', 'failed') NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_material_chunk (material_id, chunk_index),
    KEY idx_class_status (class_id, index_status),
    FULLTEXT KEY ft_chunks_text (chunk_text) WITH PARSER ngram,
    CONSTRAINT fk_chunks_material FOREIGN KEY (material_id)
        REFERENCES materials (id) ON DELETE CASCADE,
    CONSTRAINT fk_chunks_entry FOREIGN KEY (knowledge_entry_id)
        REFERENCES knowledge_entries (id) ON DELETE CASCADE,
    CONSTRAINT fk_chunks_class FOREIGN KEY (class_id)
        REFERENCES classes (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
