"""Materials routes: teacher upload (transactional ingest), class-scoped list/detail/download."""
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request, send_file

from app.db.connection import get_connection
from app.middleware.auth import auth_required
from app.middleware.role import role_required
from app.repositories.materials import MaterialsRepository
from app.services.upload import UploadValidationError, save_upload

materials_bp = Blueprint("materials", __name__)


@materials_bp.route("/materials", methods=["POST"])
@auth_required
@role_required("teacher")
def upload_material():
    """Teacher uploads a material. class_id comes from the server session."""
    if "file" not in request.files:
        return jsonify({"error": "no file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "empty filename"}), 400

    try:
        record = save_upload(
            current_app.config["DB"],
            Path(current_app.config["UPLOAD_ROOT"]),
            file=file,
            class_id=g.current_user["classId"],
            uploader_id=g.current_user["userId"],
            max_size_mb=current_app.config["UPLOAD_MAX_SIZE_MB"],
        )
    except UploadValidationError as exc:
        return jsonify({"error": str(exc)}), exc.status
    except Exception:
        return jsonify({"error": "upload failed"}), 500

    # Lesson 4: post-commit indexing (chunk -> embed -> vectors). The material
    # is already committed; indexing failure never changes the 201 result —
    # affected chunks are marked failed and can be rebuilt by the teacher.
    try:
        from app.services.indexing import index_material

        summary = index_material(
            current_app.config["DB"],
            current_app.config["QDRANT"],
            current_app.config["APP_CONFIG"],
            int(record["id"]),
            strategy="auto",
        )
        record["indexing"] = summary
    except Exception:
        current_app.logger.exception("post-upload indexing failed")

    return jsonify(record), 201


@materials_bp.route("/materials/<int:material_id>/reindex", methods=["POST"])
@auth_required
@role_required("teacher")
def reindex_material(material_id: int):
    """Teacher rebuilds chunks + vectors for one of THIS class's materials."""
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        repo = MaterialsRepository(conn)
        material = repo.find_by_id_scoped_to_class(material_id, class_id)
    finally:
        conn.close()
    if material is None:
        # Cross-class and non-existent are indistinguishable.
        return jsonify({"error": "not found"}), 404

    body = request.get_json(silent=True) or {}
    strategy = body.get("strategy", "auto")
    kwargs = {"strategy": strategy}
    if strategy == "custom":
        kwargs["chunk_size"] = body.get("chunk_size")
        kwargs["overlap_ratio"] = float(body.get("overlap_ratio", 0.0))
        kwargs["strip_urls"] = bool(body.get("strip_urls", False))
        kwargs["strip_emails"] = bool(body.get("strip_emails", False))
        kwargs["collapse_spaces"] = bool(body.get("collapse_spaces", False))

    try:
        from app.services.chunking import ChunkParamError
        from app.services.indexing import reindex_material as run_reindex

        summary = run_reindex(
            current_app.config["DB"],
            current_app.config["QDRANT"],
            current_app.config["APP_CONFIG"],
            material_id,
            **kwargs,
        )
    except ChunkParamError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("reindex failed")
        return jsonify({"error": "reindex failed"}), 500

    return jsonify(summary), 200


@materials_bp.route("/materials", methods=["GET"])
@auth_required
def list_materials():
    """Return materials scoped to the current user's class."""
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        repo = MaterialsRepository(conn)
        materials = repo.find_by_class(class_id)
    finally:
        conn.close()
    return jsonify({"materials": materials, "classId": class_id}), 200


@materials_bp.route("/materials/<int:material_id>", methods=["GET"])
@auth_required
def get_material(material_id: int):
    """Return a single material, scoped to current user's class (cross-class → 404)."""
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        repo = MaterialsRepository(conn)
        material = repo.find_by_id_scoped_to_class(material_id, class_id)
    finally:
        conn.close()
    if material is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(material), 200


@materials_bp.route("/materials/<int:material_id>/download", methods=["GET"])
@auth_required
def download_material(material_id: int):
    """Download a material file. Cross-class and non-existent → same-shape 404."""
    class_id = g.current_user["classId"]
    conn = get_connection(current_app.config["DB"])
    try:
        repo = MaterialsRepository(conn)
        material = repo.find_by_id_scoped_to_class(material_id, class_id)
    finally:
        conn.close()
    if material is None:
        # Identical body to the detail 404: cross-class is indistinguishable
        # from non-existent.
        return jsonify({"error": "not found"}), 404

    file_path = (Path(current_app.config["UPLOAD_ROOT"]) / material["storage_key"]).resolve()
    if not file_path.is_file():
        return jsonify({"error": "not found"}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=material["filename"],
    )
