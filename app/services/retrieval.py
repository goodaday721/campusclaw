"""Retrieval orchestration: keyword / vector / hybrid (RRF) class-scoped search.

The class_id used everywhere here is taken ONLY from the login session (routes
never pass a body-supplied class id). Both paths filter by class, and vector
hits are re-checked against MySQL after returning from Qdrant. Chunk text for
results always comes from MySQL — never from vector payloads.
"""
from collections import defaultdict

from app.db.connection import get_connection
from app.repositories import chunks as chunks_repo
from app.services import model_gateway, vector_store

KEYWORD = "keyword"
VECTOR = "vector"
HYBRID = "hybrid"
MODES = (KEYWORD, VECTOR, HYBRID)

NO_MATCH_MESSAGE = "资料中未找到相关内容"


class RetrievalError(Exception):
    """Base class for retrieval failures."""


class EmptyQuery(RetrievalError):
    """Empty/whitespace query → 400."""


class InvalidMode(RetrievalError):
    """Unknown retrieval mode → 400."""


class RetrievalUnavailable(RetrievalError):
    """Embedding gateway or Qdrant unavailable → 503."""


def rrf_fuse(rank_lists: list[list[int]], k: float) -> list[int]:
    """Reciprocal rank fusion: score = Σ 1/(k + rank), ranks start at 1.

    An absent path simply contributes nothing.
    """
    scores: dict[int, float] = defaultdict(float)
    for ranked in rank_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[int(chunk_id)] += 1.0 / (k + rank)
    return sorted(scores, key=lambda cid: (-scores[cid], cid))


def _material_titles(conn, material_ids: set[int]) -> dict[int, str]:
    if not material_ids:
        return {}
    placeholders = ",".join(["%s"] * len(material_ids))
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id, filename FROM materials WHERE id IN ({placeholders})",
            tuple(material_ids),
        )
        return {int(r["id"]): r["filename"] for r in cur.fetchall()}


def _make_excerpt(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _vector_path(db: dict, qcfg: dict, config, class_id: int, query: str) -> list[int]:
    """Embed the query, search Qdrant (class filter + threshold), return ids."""
    vectors = model_gateway.embed_texts(config, [query])
    if not vectors:
        return []
    qdrant_hits = vector_store.search(
        qcfg,
        class_id,
        vectors[0],
        limit=config.search_path_limit,
        score_threshold=config.vector_threshold,
    )
    return [cid for cid, _score in qdrant_hits]


def search(
    db: dict,
    qcfg: dict,
    config,
    class_id: int,
    query: str,
    mode: str = HYBRID,
    final_limit: int | None = None,
    excerpt_limit: int | None = None,
) -> list[dict]:
    """Run the chosen retrieval mode and return assembled, sourced hits.

    excerpt_limit defaults to config.excerpt_limit (search-result display);
    the ask flow passes a larger value so prompts carry real grounding text.
    """
    if query is None or not str(query).strip():
        raise EmptyQuery("query must not be empty")
    query = str(query).strip()
    if mode not in MODES:
        raise InvalidMode(f"mode must be one of {', '.join(MODES)}")

    conn = get_connection(db)
    try:
        if mode == KEYWORD:
            ordered_ids = chunks_repo.keyword_search(
                conn, class_id, query, config.search_path_limit
            )
        else:
            try:
                vector_ids = _vector_path(db, qcfg, config, class_id, query)
            except (
                model_gateway.GatewayError,
                vector_store.VectorStoreUnavailable,
                vector_store.VectorDimensionMismatch,
            ) as exc:
                # Per spec: vector/hybrid surface 503 rather than silently
                # degrading, so users never mistake partial results for hybrid.
                raise RetrievalUnavailable(str(exc)) from exc

            if mode == VECTOR:
                ordered_ids = vector_ids
            else:
                keyword_ids = chunks_repo.keyword_search(
                    conn, class_id, query, config.search_path_limit
                )
                ordered_ids = rrf_fuse(
                    [keyword_ids, vector_ids], k=config.rrf_k
                )

        hits = _assemble_with_limit(
            conn,
            ordered_ids,
            class_id,
            final_limit or config.search_final_limit,
            excerpt_limit if excerpt_limit is not None else config.excerpt_limit,
        )
        return hits
    finally:
        conn.close()


def _assemble_with_limit(
    conn, ordered_ids: list[int], class_id: int, final_limit: int, excerpt_limit: int
) -> list[dict]:
    """Re-fetch ready chunks scoped to the class, preserving ranking order."""
    rows = chunks_repo.get_ready_by_ids_scoped(conn, ordered_ids, class_id)
    titles = _material_titles(
        conn,
        {rows[cid]["material_id"] for cid in ordered_ids if cid in rows},
    )
    hits = []
    for cid in ordered_ids:
        row = rows.get(cid)
        if row is None:
            continue
        material_id = int(row["material_id"])
        hits.append(
            {
                "chunkId": int(row["id"]),
                "materialId": material_id,
                "materialTitle": titles.get(material_id, ""),
                "chunkIndex": int(row["chunk_index"]),
                "charStart": int(row["char_start"]),
                "charEnd": int(row["char_end"]),
                "excerpt": _make_excerpt(row["chunk_text"], excerpt_limit),
                "materialUrl": f"/materials/{material_id}",
            }
        )
        if len(hits) >= final_limit:
            break
    return hits
