from flask import request, jsonify
from . import bp

@bp.post("/contact")
def api_contact():
    # stub endpoint for the blank frontend
    data = request.get_json() or {}
    if not all(k in data for k in ("name","email","message")):
        return jsonify({"error":"missing fields"}), 400
    return jsonify({"ok": True})

@bp.get("/leaderboard")
def api_leaderboard():
    # stub leaderboard
    return jsonify([{"player":"anon","score":42}])
