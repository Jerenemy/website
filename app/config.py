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
    WTT_DATABASE_PATH = os.getenv(
        "WTT_DATABASE_PATH", os.path.join(_project_root, "instance", "wtt.sqlite3")
    )

    CLASH_ROYALE_API_TOKEN = os.getenv("CLASH_ROYALE_API_TOKEN") or os.getenv("CLASH_ROYALE_API_KEY")
    CLASH_ROYALE_API_BASE_URL = os.getenv("CLASH_ROYALE_API_BASE_URL", "https://api.clashroyale.com/v1")
    CLASH_ROYALE_DATABASE_PATH = os.getenv("CLASH_ROYALE_DATABASE_PATH", os.path.join(_project_root, "instance", "clash.sqlite3"))
    # /scic/reviews: what people write about my tutoring (instance/, untracked like the other stores)
    SCIC_REVIEWS_DATABASE_PATH = os.getenv("SCIC_REVIEWS_DATABASE_PATH", os.path.join(_project_root, "instance", "scic_reviews.sqlite3"))

    # Job application bot (getmeajob `serve`): private API on the same machine, same token as its REVIEW_API_TOKEN.
    JOBBOT_API_URL = os.getenv("JOBBOT_API_URL", "http://127.0.0.1:5003")
    JOBBOT_API_TOKEN = os.getenv("JOBBOT_API_TOKEN")
    # What the phone shortcut that forwards companies' text messages sends (POST /admin/jobs/texts). It can
    # only file texts, so the phone never holds the admin login or the bot's own token.
    JOBBOT_TEXT_TOKEN = os.getenv("JOBBOT_TEXT_TOKEN")

    # Blink (/blink): the App Clip can't write to CloudKit, so it asks this site to delete a viewed photo.
    # The server-to-server key is made in CloudKit Console; the private key file stays on the server.
    BLINK_CK_CONTAINER = os.getenv("BLINK_CK_CONTAINER", "iCloud.com.jeremyzay.blink")
    BLINK_CK_ENV = os.getenv("BLINK_CK_ENV", "production")
    BLINK_CK_KEY_ID = os.getenv("BLINK_CK_KEY_ID")
    BLINK_CK_KEY_PATH = os.getenv("BLINK_CK_KEY_PATH")
    # Blink's numeric App Store ID, for the App Clip banner on Blink links (shown only once it's set).
    BLINK_APP_STORE_ID = os.getenv("BLINK_APP_STORE_ID")
    BLINK_REPORTS_DIR = os.getenv("BLINK_REPORTS_DIR", os.path.join(_project_root, "instance", "blink_reports"))

    # Sonar's own site on this server (sonar.show); /admin/sonar reads its share counts with the token.
    SONAR_SITE_URL = os.getenv("SONAR_SITE_URL", "http://127.0.0.1:8002")
    SONAR_STATS_TOKEN = os.getenv("SONAR_STATS_TOKEN")

    # CEO outreach dashboards (/admin/outreach): the Mac's routine POSTs its leads and scoreboard to
    # /admin/outreach/sync with this token and gets the reply examples back. Data stays in instance/.
    OUTREACH_SYNC_TOKEN = os.getenv("OUTREACH_SYNC_TOKEN")
    OUTREACH_DATA_DIR = os.getenv("OUTREACH_DATA_DIR", os.path.join(_project_root, "instance", "outreach"))

    SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
    ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    # The works: the live file is the server's own (written by /admin/portfolio, untracked); the
    # seed is tracked and only fills a missing live file, or lends it words via `flask portfolio-copy`.
    PORTFOLIO_DATA_PATH = os.getenv(
        "PORTFOLIO_DATA_PATH",
        os.path.join(_project_root, "app", "data", "portfolio.json"),
    )
    PORTFOLIO_SEED_PATH = os.getenv(
        "PORTFOLIO_SEED_PATH",
        os.path.join(_project_root, "app", "data", "portfolio.seed.json"),
    )
    SITE_SETTINGS_PATH = os.getenv(
        "SITE_SETTINGS_PATH",
        os.path.join(_project_root, "app", "data", "site_settings.json"),
    )
    SITE_FILES_DIR = os.getenv(
        "SITE_FILES_DIR",
        os.path.join(_project_root, "app", "static", "files"),
    )
    # The site's theme: static/site/themes/<name>/theme.css over static/site/tokens.css ("void" is
    # tokens.css alone). See app/design.py.
    SITE_THEME = os.getenv("SITE_THEME", "chalk")
    BLOG_POSTS_DIR = os.getenv(
        "BLOG_POSTS_DIR",
        os.path.join(_project_root, "app", "blog_posts"),
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
