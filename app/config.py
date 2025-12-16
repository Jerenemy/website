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
