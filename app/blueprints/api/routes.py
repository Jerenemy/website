import re
import time

from flask import request, jsonify, current_app, abort, redirect, url_for
from flask_mail import Message
from itsdangerous import BadSignature, URLSafeSerializer
from ...extensions import mail
from . import bp

# A contact form carries, in its hidden "t" field, when its page was served, signed so it cannot be
# made up. A message without one was posted by a script that never loaded the page; one sent
# within seconds of the page was filled in by a bot; one older than a day comes from a token
# collected and replayed.
CONTACT_MIN_SECONDS = 3
CONTACT_MAX_SECONDS = 24 * 60 * 60
# The name a spam bot gives: one run of letters, its case flipping at random ("RXfFZcgFTYqq").
# "McDonald" or "DeAndre" flip far less.
_LETTERS = re.compile(r"[A-Za-z]{8,}")


def _contact_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="contact-form")


@bp.app_template_global()
def contact_token() -> str:
    """The signed time of serving, for a contact form's hidden "t" field."""
    return _contact_serializer().dumps(int(time.time()))


def _contact_token_age(token) -> float | None:
    """Seconds since the token's page was served, or None when it is missing or not ours."""
    try:
        issued = _contact_serializer().loads(token or "")
    except BadSignature:
        return None
    return time.time() - issued if isinstance(issued, int) else None


def _is_random_letters(text: str) -> bool:
    text = text.strip()
    if not _LETTERS.fullmatch(text):
        return False
    flips = sum(a.isupper() != b.isupper() for a, b in zip(text, text[1:]))
    return flips >= 4 and sum(c.isupper() for c in text[1:]) >= 3


def _spam_reason(data) -> str | None:
    """Why this message is taken for spam, or None when it reads as a person's."""
    if data.get("website"):
        return "honeypot filled"
    age = _contact_token_age(data.get("t"))
    if age is None:
        return "no valid form token"
    if age < CONTACT_MIN_SECONDS:
        return "sent too soon after the page loaded"
    if age > CONTACT_MAX_SECONDS:
        return "form token expired"
    if _is_random_letters(str(data.get("name"))) or _is_random_letters(str(data.get("message"))):
        return "random letters"
    return None

@bp.get("/debug/mail")
def debug_mail():
    """Temporary debug endpoint to inspect mail config presence. Remove after troubleshooting."""
    if not current_app.debug:
        abort(404)

    return _mail_config_summary(current_app.config)


def _mail_config_summary(cfg):
    """The mail settings, with the username and sender reduced to whether they are set."""
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

    # A bot is told the message went (so it does not try again differently), and nothing is sent.
    reason = _spam_reason(data)
    if reason:
        current_app.logger.info("Contact form spam dropped: %s", reason)
        return reply({"ok": True})

    cfg = current_app.config
    default_sender = cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("MAIL_USERNAME")
    recipient = cfg.get("MAIL_USERNAME")

    if not default_sender or not recipient or not cfg.get("MAIL_SERVER"):
        current_app.logger.error(
            "Mail config missing required values",
            extra=_mail_config_summary(cfg),
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
