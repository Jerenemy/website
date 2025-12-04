from flask import request, jsonify, current_app
from flask_mail import Message
from ...extensions import mail
from . import bp

@bp.get("/debug/mail")
def debug_mail():
    """Temporary debug endpoint to inspect mail config presence. Remove after troubleshooting."""
    cfg = current_app.config
    return {
        "MAIL_SERVER": cfg.get("MAIL_SERVER"),
        "MAIL_PORT": cfg.get("MAIL_PORT"),
        "MAIL_USE_TLS": cfg.get("MAIL_USE_TLS"),
        "MAIL_USERNAME_present": bool(cfg.get("MAIL_USERNAME")),
        "MAIL_DEFAULT_SENDER_present": bool(cfg.get("MAIL_DEFAULT_SENDER")),
    }

@bp.post("/contact")
def api_contact():
    data = request.get_json() or {}
    name, email, message = data.get("name"), data.get("email"), data.get("message")

    if not all([name, email, message]):
        return jsonify({"error": "Missing fields"}), 400

    cfg = current_app.config
    default_sender = cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("MAIL_USERNAME")
    recipient = cfg.get("MAIL_USERNAME")

    if not default_sender or not recipient or not cfg.get("MAIL_SERVER"):
        current_app.logger.error(
            "Mail config missing required values",
            extra={
                "MAIL_SERVER": cfg.get("MAIL_SERVER"),
                "MAIL_PORT": cfg.get("MAIL_PORT"),
                "MAIL_USE_TLS": cfg.get("MAIL_USE_TLS"),
                "MAIL_USERNAME_present": bool(cfg.get("MAIL_USERNAME")),
                "MAIL_DEFAULT_SENDER_present": bool(cfg.get("MAIL_DEFAULT_SENDER")),
            },
        )
        return jsonify({"error": "Email service not configured"}), 500

    msg = Message(
        subject=f"New message from {name}",
        sender=default_sender,
        recipients=[recipient],  # send to yourself
        body=f"From: {name} <{email}>\n\n{message}",
    )

    try:
        current_app.logger.info(
            "Attempting to send contact email",
            extra={
                "recipient": recipient,
                "mail_server": cfg.get("MAIL_SERVER"),
                "mail_port": cfg.get("MAIL_PORT"),
                "mail_use_tls": cfg.get("MAIL_USE_TLS"),
            },
        )
        mail.send(msg)
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.exception("MAIL ERROR")
        return jsonify({"error": "Failed to send email"}), 500
    
@bp.get("/leaderboard")
def api_leaderboard():
    # stub leaderboard
    return jsonify([{"player":"anon","score":42}])
