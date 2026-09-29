"""Indexing orchestration: chunk -> embed -> upsert vectors, failure-tolerant.

The material file and the materials/knowledge_entries rows are committed BEFORE
this runs. Any indexing failure never removes them: affected chunks are marked
index_status='failed' and no partial vectors are written, so a teacher can
rebuild the index later. Existing materials are never auto-rechunked.
"""
import logging

from app.db.connection import get_connection
from app.repositories import chunks as chunks_repo
from app.repositories import knowledge as knowledge_repo
from app.services import chunking, model_gateway, vector_store

logger = logging.getLogger(__name__)


def _chunks_to_rows(entry: dict, chunks: list[chunking.Chunk], strategy: str) -> list[dict]:
    return [
        {
            "material_id": entry["material_id"],
            "knowledge_entry_id": entry["id"],
            "class_id": entry["class_id"],
            "chunk_index": c.chunk_index,
            "chunk_text": c.text,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "strategy": strategy,
            "index_status": "ready",
        }
        for c in chunks
    ]


def index_material(
    db: dict,
    qcfg: dict,
    config,
    material_id: int,
    *,
    strategy: str = "auto",
    chunk_size: int | None = None,
    overlap_ratio: float = 0.0,
    strip_urls: bool = False,
    strip_emails: bool = False,
    collapse_spaces: bool = False,
) -> dict:
    """Chunk one material's entry, embed, and upsert vectors.

    Returns a summary {"material_id", "chunks_total", "chunks_ready",
    "chunks_failed"}. Embedding/Qdrant failures mark all chunks 'failed' but do
    not raise — the committed material stays usable (keyword search works on
    ready chunks; failed chunks are excluded until a teacher rebuilds).
    """
    conn = get_connection(db)
    try:
        entry = knowledge_repo.find_by_material_id(conn, material_id)
        if entry is None:
            return {
                "material_id": material_id,
                "chunks_total": 0,
                "chunks_ready": 0,
                "chunks_failed": 0,
            }

        chunks = chunking.chunk_text(
            entry["content"],
            strategy,
            chunk_size=chunk_size,
            overlap_ratio=overlap_ratio,
            strip_urls=strip_urls,
            strip_emails=strip_emails,
            collapse_spaces=collapse_spaces,
        )
        if not chunks:
            return {
                "material_id": material_id,
                "chunks_total": 0,
                "chunks_ready": 0,
                "chunks_failed": 0,
            }

        # Chunks are immediately usable by keyword FULLTEXT search.
        chunk_ids = chunks_repo.insert_many(
            conn, _chunks_to_rows(entry, chunks, strategy)
        )
        conn.commit()

        try:
            vectors = model_gateway.embed_texts(config, [c.text for c in chunks])
            if len(vectors) != len(chunks):
                raise model_gateway.GatewayUnavailable(
                    "embedding count does not match chunk count"
                )
            vector_store.ensure_collection(qcfg, len(vectors[0]))
            points = [
                {
                    "id": cid,
                    "vector": vec,
                    "payload": {
                        # Identifiers only — chunk text never enters Qdrant.
                        "chunk_id": cid,
                        "class_id": entry["class_id"],
                        "material_id": entry["material_id"],
                        "knowledge_entry_id": entry["id"],
                        "chunk_index": c.chunk_index,
                    },
                }
                for cid, vec, c in zip(chunk_ids, vectors, chunks)
            ]
            vector_store.upsert(qcfg, points)
            chunks_repo.mark_embedding_status(conn, chunk_ids, "ready")
            conn.commit()
            logger.info(
                "indexed material %s: %s chunks ready", material_id, len(chunk_ids)
            )
            return {
                "material_id": material_id,
                "chunks_total": len(chunk_ids),
                "chunks_ready": len(chunk_ids),
                "chunks_failed": 0,
            }
        except (
            model_gateway.GatewayError,
            vector_store.VectorStoreUnavailable,
            vector_store.VectorDimensionMismatch,
        ) as exc:
            # Material + chunk TEXT stay ready (keyword search still works);
            # only the vector embedding is marked failed; no partial vectors.
            chunks_repo.mark_embedding_status(conn, chunk_ids, "failed")
            conn.commit()
            logger.warning(
                "vector indexing failed for material %s: %s", material_id, exc
            )
            return {
                "material_id": material_id,
                "chunks_total": len(chunk_ids),
                "chunks_ready": 0,
                "chunks_failed": len(chunk_ids),
            }
    finally:
        conn.close()


def reindex_material(db: dict, qcfg: dict, config, material_id: int, **kwargs) -> dict:
    """Delete a material's old vectors/chunks and index it again."""
    # Best-effort vector cleanup: stale points whose ids no longer exist are
    # filtered out by the MySQL re-check in retrieval even if this fails.
    try:
        vector_store.delete_by_material(qcfg, material_id)
    except vector_store.VectorStoreUnavailable as exc:
        logger.warning("could not delete old vectors for material %s: %s", material_id, exc)

    conn = get_connection(db)
    try:
        chunks_repo.delete_by_material(conn, material_id)
        conn.commit()
    finally:
        conn.close()

    return index_material(db, qcfg, config, material_id, **kwargs)


def backfill_indexes(db: dict, qcfg: dict, config) -> dict:
    """Index materials that have no chunks yet (startup backfill, auto only)."""
    conn = get_connection(db)
    try:
        missing = chunks_repo.find_materials_without_chunks(conn)
    finally:
        conn.close()

    indexed = 0
    for row in missing:
        try:
            index_material(db, qcfg, config, int(row["material_id"]), strategy="auto")
            indexed += 1
        except Exception as exc:  # never block startup on one bad material
            logger.warning(
                "startup backfill failed for material %s: %s",
                row["material_id"],
                exc,
            )
    if indexed:
        logger.info("startup backfill indexed %s material(s)", indexed)
    return {"materials_indexed": indexed}
