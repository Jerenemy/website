from flask import request, jsonify, current_app, abort, redirect, url_for
from flask_mail import Message
from ...extensions import mail
from . import bp

@bp.get("/debug/mail")
def debug_mail():
    """Temporary debug endpoint to inspect mail config presence. Remove after troubleshooting."""
    if not current_app.debug:
        abort(404)

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
    # JSON from static/js/contact.js (and the zaychess support and eqoscan pages); the contact
    # page's own form, posted by a browser without JavaScript, arrives form-encoded and is
    # answered with the contact page again, its outcome in the status line (303: a reload does
    # not post twice).
    as_page = not request.is_json
    data = request.form if as_page else (request.get_json(silent=True) or {})

    def reply(payload, status=200):
        if as_page:
            outcome = "sent" if status == 200 else "missing" if status == 400 else "failed"
            return redirect(url_for("public.contact", status=outcome), code=303)
        return jsonify(payload), status

    if not isinstance(data, dict) and not as_page:
        return reply({"error": "Missing fields"}, 400)
    name, email, message = data.get("name"), data.get("email"), data.get("message")

    if not all([name, email, message]):
        return reply({"error": "Missing fields"}, 400)

    # The contact page's hidden field: no person fills it in; a form-filling bot does. It is told
    # the message went, and nothing is sent.
    if data.get("website"):
        current_app.logger.info("Contact form honeypot filled; message dropped")
        return reply({"ok": True})

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
        return reply({"error": "Email service not configured"}, 500)

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
        return reply({"ok": True})
    except Exception as e:
        current_app.logger.exception("MAIL ERROR")
        return reply({"error": "Failed to send email"}, 500)
    
@bp.get("/leaderboard")
def api_leaderboard():
    # stub leaderboard
    return jsonify([{"player":"anon","score":42}])
