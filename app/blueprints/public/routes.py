from flask import abort, current_app, render_template, send_from_directory
from werkzeug.exceptions import NotFound

from ...blog import get_blog_store
from ...portfolio import get_portfolio_store
from ...site_settings import get_site_settings_store
from . import bp

ZAYCHESS_CURRENT_VERSION = "1.2"
ZAYCHESS_MIN_MACOS = "12.0"

@bp.get("/")
def index():
    store = get_portfolio_store()
    items = store.list_items()
    settings = get_site_settings_store().get_settings()
    return render_template("index.html", portfolio_items=items, site_settings=settings)

@bp.get("/game")
def game():
    return render_template("game.html")

@bp.get("/blog")
def blog():
    posts = get_blog_store().list_posts()
    return render_template("blog.html", posts=posts)


@bp.get("/blog/<slug>")
def blog_post(slug: str):
    post = get_blog_store().get_post(slug)
    if post is None:
        abort(404)
    return render_template("blog_post.html", post=post)

@bp.get("/resume")
def resume():
    # serves the file from static/files/
    settings = get_site_settings_store().get_settings()
    filename = settings.get("resume_filename") or "resume.pdf"
    files_dir = current_app.config["SITE_FILES_DIR"]
    try:
        return send_from_directory(files_dir, filename, mimetype="application/pdf")
    except NotFound:
        if filename != "resume.pdf":
            return send_from_directory(files_dir, "resume.pdf", mimetype="application/pdf")
        raise
    
@bp.get("/poster-rl-2024")
def poster_rl_2024():
    # serves the file from static/files/
    return send_from_directory(
        current_app.static_folder + "/files",
        "poster-rl-2024.pdf",
        mimetype="application/pdf"
    )
    
@bp.get("/poster-diffusion-2025")
def poster_diffusion_2025():
    # serves the file from static/files/
    return send_from_directory(
        current_app.static_folder + "/files",
        "poster-diffusion-2025.pdf",
        mimetype="application/pdf"
    )
    
@bp.get('/zaychess', strict_slashes=False)  
def zaychess():
    return render_template('zaychess/zaychess.html')

@bp.get('/zaychess/support', strict_slashes=False)
def zaychess_support():
    return render_template(
        'zaychess/zaychess_support.html',
        zaychess_current_version=ZAYCHESS_CURRENT_VERSION,
        zaychess_min_macos=ZAYCHESS_MIN_MACOS,
    )

@bp.get('/zaychess/privacy', strict_slashes=False)
def zaychess_privacy():
    return render_template(
        'zaychess/zaychess_privacy.html',
        zaychess_current_version=ZAYCHESS_CURRENT_VERSION,
    )

@bp.get('/eqoscan')  
def eqoscan():
    return render_template('eqoscan.html')

@bp.get('/moinllm')
def moinllm():
    return render_template('moinllm.html')

@bp.get('/deltalab')
def deltalab():
    return render_template('attack_target_graph_interactive_v1.html')

@bp.get('/sonar', strict_slashes=False)
def sonar():
    return render_template('sonar/sonar.html')

@bp.get('/sonar/support', strict_slashes=False)
def sonar_support():
    return render_template('sonar/sonar_support.html')

@bp.get('/sonar/privacy', strict_slashes=False)
def sonar_privacy():
    return render_template('sonar/sonar_privacy.html')
