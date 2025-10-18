from flask import Flask
from .blueprints.public import bp as public_bp
from .blueprints.api import bp as api_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(public_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    return app
