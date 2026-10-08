"""What every page's template needs to look like the rest of the site (templates/layout.html):
the active theme, the frame's name and links, and where the page sits in the loop of works.

The look itself is in static/site/tokens.css (every value) and static/site/site.css (every piece);
a theme is static/site/themes/<name>.css. The default theme is the SITE_THEME setting (empty or
"void": tokens.css alone). Any page previews another with ?theme=<name>, which a cookie keeps
for the rest of the visit; ?theme=void clears it.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Flask, current_app, render_template, request, url_for

THEME_COOKIE = "theme"
DEFAULT_THEME = "void"


def _themes(static_folder: str) -> set[str]:
    return {p.stem for p in (Path(static_folder) / "site" / "themes").glob("*.css")}


def _requested_theme() -> str:
    """The theme for this request: a ?theme= preview, the visitor's kept preview, or the site's."""
    known = _themes(current_app.static_folder)
    for candidate in (request.args.get("theme"), request.cookies.get(THEME_COOKIE)):
        if candidate == DEFAULT_THEME or candidate in known:
            return candidate
    configured = (current_app.config.get("SITE_THEME") or DEFAULT_THEME).strip()
    return configured if configured in known else DEFAULT_THEME


def _work_nav(works: list[dict]) -> dict | None:
    """This page's place among the works, when it is one (or one of its own pages, such as
    /sonar/support for /sonar): its number, the total, and its neighbours in the loop."""
    path = request.path.rstrip("/") or "/"
    for i, work in enumerate(works):
        href = work["href"].rstrip("/")
        if not href.startswith("/") or href == "":
            continue
        if path == href or path.startswith(href + "/"):
            n = len(works)
            return {
                "work": work,
                "no": i + 1,
                "total": n,
                "prev": works[(i - 1) % n] if n > 1 else None,
                "next": works[(i + 1) % n] if n > 1 else None,
                # The homepage opens its loop at the work named in the hash (static/home/src/main.js).
                "index_href": url_for("public.index") + ("#" + work["id"] if i else ""),
            }
    return None


def init_app(app: Flask) -> None:
    app.config.setdefault("SITE_THEME", DEFAULT_THEME)

    @app.context_processor
    def design_context() -> dict:
        # Imported here: the public blueprint owns the works and the frame's links.
        from .blueprints.public.routes import _home_person, _home_works

        theme = _requested_theme()
        try:
            works = _home_works()
        except Exception:   # a page must render even if the portfolio cannot be read
            current_app.logger.exception("Works unavailable for the page frame")
            works = []
        return {
            "site_theme": theme,
            "site_theme_css": None if theme == DEFAULT_THEME else url_for("static", filename=f"site/themes/{theme}.css"),
            "frame": _home_person(),
            "work_nav": _work_nav(works),
            "year": date.today().year,
        }

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code="404", heading="Nothing here"), 404

    @app.after_request
    def keep_theme_preview(response):
        chosen = request.args.get("theme")
        if chosen is None:
            return response
        if chosen == DEFAULT_THEME:
            response.delete_cookie(THEME_COOKIE)
        elif chosen in _themes(current_app.static_folder):
            response.set_cookie(THEME_COOKIE, chosen, max_age=60 * 60 * 24 * 30, samesite="Lax", httponly=True)
        return response
