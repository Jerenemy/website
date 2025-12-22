import os
from dotenv import dotenv_values

class Config:
    # Ensure .env values are loaded even if the process cwd differs or load_dotenv was skipped.
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _env_path = os.path.join(_project_root, ".env")
    _dotenv_values = dotenv_values(_env_path)

    # Pre-populate os.environ for keys that are missing so os.getenv picks them up below.
    for _k, _v in _dotenv_values.items():
        if _k not in os.environ and _v is not None:
            os.environ[_k] = str(_v)

    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME)
    EAR_BASE_DIR = os.getenv("EAR_BASE_DIR")

    SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
    ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    PORTFOLIO_DATA_PATH = os.getenv(
        "PORTFOLIO_DATA_PATH",
        os.path.join(_project_root, "app", "data", "portfolio.json"),
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    _max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "6"))
    MAX_CONTENT_LENGTH = _max_upload_mb * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    UPLOADS_DIR = os.getenv(
        "UPLOADS_DIR",
        os.path.join(_project_root, "app", "static", "img", "uploads"),
    )
    UPLOADS_THUMBS_DIR = os.getenv(
        "UPLOADS_THUMBS_DIR",
        os.path.join(_project_root, "app", "static", "img", "uploads", "thumbs"),
    )
