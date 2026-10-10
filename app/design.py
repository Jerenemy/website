"""What every page's template needs to look like the rest of the site (templates/layout.html):
the active theme, the frame's name and links, and where the page sits in the loop of works.

The look itself is in static/site/tokens.css (every value) and static/site/site.css (every piece);
a theme is a folder, static/site/themes/<name>/: theme.css (the tokens it overrides) and, when
it also changes the homepage's world, scene.js (static/home/src/theme.js is the contract). The
default theme is the SITE_THEME setting (empty or "void": tokens.css alone and the scene's own
world). Any page switches to another with ?theme=<name> (the switcher in every page's frame),
which a cookie keeps for the rest of the visit; ?theme=void clears it. A theme folder holding a
file named `hidden` is kept out of the switcher but still answers to ?theme=<name>: a look in the
making, previewable by its URL.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Flask, current_app, render_template, request, url_for

THEME_COOKIE = "theme"
DEFAULT_THEME = "void"


def _themes(static_folder: str) -> set[str]:
    """The themes on disk: every folder of static/site/themes with a theme.css."""
    return {p.parent.name for p in (Path(static_folder) / "site" / "themes").glob("*/theme.css")}


def _hidden(static_folder: str) -> set[str]:
    """The themes on disk that sit out of the switcher: those whose folder holds a `hidden` file."""
    return {p.parent.name for p in (Path(static_folder) / "site" / "themes").glob("*/hidden")}


def _has_scene(static_folder: str, theme: str) -> bool:
    return (Path(static_folder) / "site" / "themes" / theme / "scene.js").is_file()


def theme_choices(static_folder: str, current: str) -> list[dict]:
    """The switcher's rows (templates/partials/_themes.html): the default first, then the rest by name,
    the hidden ones left out (the current theme stays listed even when hidden, so it reads as chosen)."""
    names = [DEFAULT_THEME] + sorted(name for name in _themes(static_folder) - {DEFAULT_THEME}
                                     if name == current or name not in _hidden(static_folder))
    return [{"name": name, "current": name == current} for name in names]


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
        static_folder = current_app.static_folder
        return {
            "site_theme": theme,
            "site_theme_css": None if theme == DEFAULT_THEME else url_for("static", filename=f"site/themes/{theme}/theme.css"),
            # The scene's side of the theme (static/home/src/theme.js loads it); None: the scene's own world.
            "site_theme_scene": url_for("static", filename=f"site/themes/{theme}/scene.js") if theme != DEFAULT_THEME and _has_scene(static_folder, theme) else None,
            "site_themes": theme_choices(static_folder, theme),
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
