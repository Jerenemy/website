from flask import Flask
from dotenv import load_dotenv
from .blueprints.public import bp as public_bp
from .blueprints.api import bp as api_bp
from .extensions import mail
from .config import Config


def create_app():
    load_dotenv()  # Load .env values for local/dev deployments
    app = Flask(__name__)
    app.config.from_object(Config)

    # Log mail config visibility (excluding password) to help diagnose missing env vars.
    mail_keys = ["MAIL_SERVER", "MAIL_PORT", "MAIL_USE_TLS", "MAIL_USERNAME", "MAIL_DEFAULT_SENDER"]
    try:
        app.logger.info(
            "Mail config snapshot (password omitted)",
            extra={k: app.config.get(k) for k in mail_keys},
        )
    except Exception:
        app.logger.exception("Failed to log mail config snapshot")

    # register blueprints
    app.register_blueprint(public_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    # initialize extensions
    mail.init_app(app)
    return app
