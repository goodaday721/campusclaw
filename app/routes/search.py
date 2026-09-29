"""POST /search — class-scoped keyword / vector / hybrid retrieval.

class_id is NEVER read from the request body: only the login session's class is
used (see retrieval.search). Unrelated queries return 200 with an empty hit
list + a fixed message; empty queries return 400; vector dependency failures
return 503 while keyword keeps working.
"""
from flask import Blueprint, current_app, g, jsonify, request

from app.middleware.auth import auth_required
from app.services import retrieval

search_bp = Blueprint("search", __name__)


@search_bp.route("/search", methods=["POST"])
@auth_required
def search_materials():
    body = request.get_json(silent=True) or {}
    # NOTE: body.get("class_id") is deliberately never read.
    query = body.get("query", "")
    mode = body.get("mode", retrieval.HYBRID)
    class_id = g.current_user["classId"]

    try:
        hits = retrieval.search(
            current_app.config["DB"],
            current_app.config["QDRANT"],
            current_app.config["APP_CONFIG"],
            class_id,
            query,
            mode=mode,
        )
    except retrieval.EmptyQuery as exc:
        return jsonify({"error": str(exc)}), 400
    except retrieval.InvalidMode as exc:
        return jsonify({"error": str(exc)}), 400
    except retrieval.RetrievalUnavailable as exc:
        return jsonify({"error": "retrieval unavailable", "detail": str(exc)}), 503

    response = {"query": query.strip(), "mode": mode, "hits": hits}
    if not hits:
        response["message"] = retrieval.NO_MATCH_MESSAGE
    return jsonify(response), 200
