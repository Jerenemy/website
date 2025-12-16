from __future__ import annotations

from pathlib import Path

from flask import current_app, jsonify, render_template, request, send_from_directory

from . import bp

_engine = None
_engine_error = None


def _engine_base_dir() -> Path:
    configured = current_app.config.get("EAR_BASE_DIR")
    if configured:
        return Path(configured)
    return Path(current_app.root_path).parent / "ear_data"


def get_engine(warm: bool = True):
    global _engine, _engine_error
    if _engine is not None or _engine_error is not None:
        return _engine
    if not warm:
        return None
    try:
        from app.ear.engine import EarEngine

        base_dir = _engine_base_dir()
        if not base_dir.exists():
            _engine_error = f"Ear data directory not found at {base_dir}"
            current_app.logger.error(_engine_error)
            return None

        _engine = EarEngine(base_dir, data_url_prefix="/ear/data")
    except Exception as exc:  # noqa: BLE001 - capture to surface to user cleanly
        current_app.logger.exception("Ear engine failed to initialize")
        _engine_error = exc
    return _engine


@bp.get("/")
def ear_home():
    # Avoid warming on page load; the engine spins up on first query.
    return render_template("ear.html", ear_error=_engine_error)


@bp.get("/data/<path:filename>")
def serve_data(filename):
    engine = get_engine()
    if engine is None:
        message = "Ear backend unavailable"
        if _engine_error:
            message = f"Ear backend unavailable: {_engine_error}"
        return jsonify({"error": message}), 503
    return send_from_directory(engine.dataset_root, filename)


@bp.post("/query")
def query_endpoint():
    engine = get_engine()
    if engine is None:
        message = "Ear backend unavailable"
        if _engine_error:
            message = f"Ear backend unavailable: {_engine_error}"
        return jsonify({"error": message}), 503

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    try:
        result = engine.query(file)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - bubble up to client, log internally
        try:
            from app.ear.engine import EarDatasetEmpty
        except Exception:
            EarDatasetEmpty = None

        current_app.logger.exception("Ear query failed")
        if EarDatasetEmpty and isinstance(exc, EarDatasetEmpty):
            return jsonify({"error": str(exc)}), 503
        return jsonify({"error": "Internal error processing query"}), 500
