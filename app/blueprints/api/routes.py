from flask import request, jsonify, current_app
from flask_mail import Message
from ...extensions import mail
from . import bp

@bp.post("/contact")
def api_contact():
    data = request.get_json() or {}
    name, email, message = data["name"], data["email"], data["message"]

    if not all([name, email, message]):
        return jsonify({"error": "Missing fields"}), 400

    msg = Message(
        subject=f"New message from {name}",
        recipients=[current_app.config["MAIL_USERNAME"]],  # send to yourself
        body=f"From: {name} <{email}>\n\n{message}"
    )

    try:
        mail.send(msg)
        return jsonify({"ok": True})
    except Exception as e:
        print("MAIL ERROR:", e)
        return jsonify({"error": "Failed to send email"}), 500
    
@bp.get("/leaderboard")
def api_leaderboard():
    # stub leaderboard
    return jsonify([{"player":"anon","score":42}])
