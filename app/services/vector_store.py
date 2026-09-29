"""Qdrant adapter: vectors keyed by knowledge_chunks.id, identifiers only.

The chunk TEXT is never stored here — payload carries class/material/entry/chunk
identifiers only. Class filtering is applied at vector-search time and the
returned ids are re-checked against MySQL afterwards.
"""
import requests
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)


class VectorStoreUnavailable(Exception):
    """Qdrant is unreachable or returned an unusable response."""


class VectorDimensionMismatch(Exception):
    """Collection exists with a different vector dimension."""


def _client(qcfg: dict) -> QdrantClient:
    return QdrantClient(
        host=qcfg["host"], port=qcfg["port"], timeout=5, prefer_grpc=False
    )


def _is_not_found(exc: UnexpectedResponse) -> bool:
    return getattr(exc, "status_code", None) == 404


def ensure_collection(qcfg: dict, dim: int) -> None:
    """Create the collection (cosine) if missing; verify dimension if present.

    Raises VectorDimensionMismatch on a dimension conflict, and
    VectorStoreUnavailable for connectivity problems.
    """
    client = _client(qcfg)
    name = qcfg["collection"]
    try:
        try:
            existing = client.get_collection(name)
        except UnexpectedResponse as exc:
            if not _is_not_found(exc):
                raise VectorStoreUnavailable(f"Qdrant returned {exc.status_code}")
            client.create_collection(
                name,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )
            return
        # qdrant-client 1.12: info.config.params.vectors (older: info.params).
        vectors_cfg = None
        config_root = getattr(existing, "config", None)
        if config_root is not None:
            vectors_cfg = getattr(getattr(config_root, "params", None), "vectors", None)
        if vectors_cfg is None:
            vectors_cfg = getattr(getattr(existing, "params", None), "vectors", None)
        existing_dim = getattr(vectors_cfg, "size", None)
        if existing_dim is not None and int(existing_dim) != int(dim):
            raise VectorDimensionMismatch(
                f"collection {name} dim={existing_dim} != embedding dim={dim}; "
                "rebuild the index"
            )
    except (ResponseHandlingException, requests.RequestException) as exc:
        raise VectorStoreUnavailable(f"Qdrant unreachable: {type(exc).__name__}")


def upsert(qcfg: dict, points: list[dict]) -> None:
    """Upsert vectors.

    Each point: {"id": chunk_id, "vector": [floats], "payload": {...}}.
    Payload holds identifiers only — never chunk text.
    """
    if not points:
        return
    client = _client(qcfg)
    try:
        client.upsert(
            qcfg["collection"],
            points=[
                models.PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p["payload"],
                )
                for p in points
            ],
            wait=True,
        )
    except (ResponseHandlingException, requests.RequestException, UnexpectedResponse) as exc:
        raise VectorStoreUnavailable(f"Qdrant upsert failed: {type(exc).__name__}")


def search(
    qcfg: dict,
    class_id: int,
    vector: list[float],
    limit: int,
    score_threshold: float,
) -> list[tuple[int, float]]:
    """Class-filtered cosine search -> [(chunk_id, score)] best first."""
    client = _client(qcfg)
    try:
        hits = client.search(
            qcfg["collection"],
            query_vector=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="class_id", match=models.MatchValue(value=class_id)
                    )
                ]
            ),
            limit=limit,
            score_threshold=score_threshold,
        )
    except (ResponseHandlingException, requests.RequestException, UnexpectedResponse) as exc:
        raise VectorStoreUnavailable(f"Qdrant search failed: {type(exc).__name__}")
    return [(int(h.id), float(h.score)) for h in hits]


def delete_by_material(qcfg: dict, material_id: int) -> None:
    """Delete every vector point of one material (reindex / material cleanup).

    Best-effort: a connectivity failure is raised so callers can decide whether
    to abort the rebuild.
    """
    client = _client(qcfg)
    try:
        client.delete(
            qcfg["collection"],
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="material_id",
                            match=models.MatchValue(value=material_id),
                        )
                    ]
                )
            ),
            wait=True,
        )
    except (ResponseHandlingException, requests.RequestException, UnexpectedResponse) as exc:
        raise VectorStoreUnavailable(f"Qdrant delete failed: {type(exc).__name__}")
