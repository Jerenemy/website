from functools import lru_cache
from pathlib import Path

from flask import abort, current_app, render_template, request, send_from_directory, url_for
from werkzeug.exceptions import NotFound

from ...blog import get_blog_store
from ...portfolio import get_portfolio_store
from ...portfolio.store import KINDS
from ...site_settings import get_site_settings_store
from . import bp

ZAYCHESS_CURRENT_VERSION = "1.2"
ZAYCHESS_MIN_MACOS = "12.0"

HOME_NAME = "Jeremy Zay"
KIND_LABELS = {kind: kind.capitalize() for kind in KINDS}   # as static/home/src/interface.js shows them
# The outcome of a contact form posted without JavaScript (api.api_contact redirects here with it);
# the same words static/js/contact.js shows.
CONTACT_STATUS = {
    "sent": "Message sent successfully!",
    "missing": "Please fill in every field.",
    "failed": "Failed to send message. Please try again.",
}


@lru_cache(maxsize=4)
def _home_modules(static_folder: str) -> tuple[str, ...]:
    """The scene's modules (static/home/src), main.js first, for home.html to preload. probe.js
    is a test hook that main.js imports only when a test asks, so visitors never fetch it."""
    names = [p.name for p in (Path(static_folder) / "home" / "src").glob("*.js") if p.name != "probe.js"]
    return tuple(sorted(names, key=lambda name: (name != "main.js", name)))


def _home_person() -> dict:
    """The name and the five links of the homepage and the contact page (relative where the
    destination is this site, so a local run stays local)."""
    return {
        "name": HOME_NAME,
        "links": [
            {"id": "resume", "label": "Résumé", "href": url_for("public.resume")},
            {"id": "writing", "label": "Writing", "href": url_for("public.blog")},
            {"id": "github", "label": "GitHub", "href": "https://github.com/Jerenemy"},
            {"id": "linkedin", "label": "LinkedIn", "href": "https://www.linkedin.com/in/jeremy-zay/"},
            {"id": "contact", "label": "Contact", "href": url_for("public.contact")},
        ],
    }


def _home_works() -> list[dict]:
    """The published works in loop order, as the scene reads them (static/home/src/content.js).
    An item saved before it had an href falls back to its image, as the old cards did; one with
    neither has nowhere to go and is left off the loop."""
    works = []
    for item in get_portfolio_store().list_items():
        href = item["href"] or (url_for("static", filename=item["image_full"]) if item["image_full"] else "")
        if not href:
            current_app.logger.warning("Portfolio item %r has no href or image; left off the homepage", item["id"])
            continue
        works.append({
            "id": item["id"],
            "title": item["title"],
            "kind": item["kind"],
            "kind_label": KIND_LABELS.get(item["kind"], ""),
            "line": item["line"],
            "href": href,
        })
    return works


@bp.get("/")
def index():
    works = _home_works()
    person = _home_person()
    settings = get_site_settings_store().get_settings()
    site_data = {
        "person": person,
        "works": [{key: w[key] for key in ("id", "title", "kind", "line", "href")} for w in works],
    }
    return render_template("home.html", works=works, person=person, site_settings=settings, site_data=site_data,
                           home_modules=_home_modules(current_app.static_folder))


@bp.get("/contact", strict_slashes=False)
def contact():
    return render_template("contact.html", person=_home_person(), site_settings=get_site_settings_store().get_settings(),
                           status=CONTACT_STATUS.get(request.args.get("status", ""), ""))


@bp.get("/me")
def me():
    """The page about the person, the homepage's first block: the words are written in its template."""
    return render_template("me.html")


@bp.get("/game")
def game():
    return render_template("works/game.html")

@bp.get("/blog")
def blog():
    posts = get_blog_store().list_posts()
    return render_template("blog/index.html", posts=posts)


@bp.get("/blog/<slug>")
def blog_post(slug: str):
    post = get_blog_store().get_post(slug)
    if post is None:
        abort(404)
    return render_template("blog/post.html", post=post)

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
    
# The posters page: each poster's text and images are its portfolio item (editable in
# /admin/portfolio, unpublished so the homepage shows them as the one Posters work); the year and
# the PDF (its route and its file) are fixed here. Newest first.
POSTERS = (
    ("diffusion", "2025", "public.poster_diffusion_2025", "files/poster-diffusion-2025.pdf"),
    ("reinforcement-learning", "2024", "public.poster_rl_2024", "files/poster-rl-2024.pdf"),
)


@bp.get("/posters", strict_slashes=False)
def posters():
    store = get_portfolio_store()
    shown = []
    for item_id, year, pdf, pdf_file in POSTERS:
        item = store.get_item(item_id)
        if item is None:
            continue
        # The page draws each poster from its PDF (static, so nginx serves and caches it) and
        # links to the poster's own address.
        shown.append({**item, "year": year, "pdf": url_for(pdf), "pdf_file": url_for("static", filename=pdf_file)})
    return render_template("works/posters.html", posters=shown)


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
    return render_template(
        'works/zaychess/zaychess.html',
        zaychess_current_version=ZAYCHESS_CURRENT_VERSION,
        zaychess_min_macos=ZAYCHESS_MIN_MACOS,
    )

@bp.get('/zaychess/support', strict_slashes=False)
def zaychess_support():
    return render_template(
        'works/zaychess/zaychess_support.html',
        zaychess_current_version=ZAYCHESS_CURRENT_VERSION,
        zaychess_min_macos=ZAYCHESS_MIN_MACOS,
    )

@bp.get('/zaychess/privacy', strict_slashes=False)
def zaychess_privacy():
    return render_template(
        'works/zaychess/zaychess_privacy.html',
        zaychess_current_version=ZAYCHESS_CURRENT_VERSION,
    )

@bp.get('/eqoscan')  
def eqoscan():
    return render_template('works/eqoscan.html')

@bp.get('/moinllm')
def moinllm():
    return render_template('works/moinllm.html')

@bp.get('/deltalab')
def deltalab():
    return render_template('works/deltalab.html')

@bp.get('/sonar', strict_slashes=False)
def sonar():
    return render_template('works/sonar/sonar.html')

@bp.get('/sonar/support', strict_slashes=False)
def sonar_support():
    return render_template('works/sonar/sonar_support.html')

@bp.get('/sonar/privacy', strict_slashes=False)
def sonar_privacy():
    return render_template('works/sonar/sonar_privacy.html')
