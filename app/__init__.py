import os
from flask import Flask
from dotenv import load_dotenv
from . import design
from .blueprints.public import bp as public_bp
from .blueprints.api import bp as api_bp
from .blueprints.admin import bp as admin_bp
from .blueprints.ear import bp as ear_bp
from .blueprints.wtt import bp as wtt_bp, init_db_command as init_wtt_command
from .blueprints.jobbot import bp as jobbot_bp
from .blueprints.clash_royale import bp as clash_bp, init_command, sync_command, verify_command
from .extensions import mail
from .config import Config


def create_app():
    # Load .env explicitly relative to the project root so it works even if cwd differs.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(project_root, ".env"))
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
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(ear_bp, url_prefix="/ear")
    app.register_blueprint(wtt_bp)          # /wtt and /admin/wtt
    app.register_blueprint(jobbot_bp)       # /admin/jobs, a client of the getmeajob API
    app.register_blueprint(clash_bp)        # /will-sucks
    for command in (init_wtt_command, init_command, sync_command, verify_command):
        app.cli.add_command(command)

    # the site's look: theme, frame and place in the loop for every template (app/design.py)
    design.init_app(app)

    # initialize extensions
    mail.init_app(app)
    return app
