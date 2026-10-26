"""What every page's template needs to look like the rest of the site (templates/layout.html):
the active theme, the frame's name and links, and where the page sits in the loop of works.

The look itself is in static/site/tokens.css (every value) and static/site/site.css (every piece);
a theme is a folder, static/site/themes/<name>/: theme.css (the tokens it overrides) and, when
it also changes the homepage's world, scene.js (static/home/src/theme.js is the contract). The
site's theme is the one chosen in /admin/settings, else the SITE_THEME setting (chalk unless set;
"void" is tokens.css alone and the scene's own world); the switcher's order is chosen there too. Any page switches to another with ?theme=<name> (the switcher in every page's frame),
which a cookie keeps for the rest of the visit; choosing the site's own theme clears it. A theme folder holding a
file named `hidden` is kept out of the switcher but still answers to ?theme=<name>: a look in the
making, previewable by its URL.
"""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from flask import Flask, current_app, g, render_template, request, url_for

THEME_COOKIE = "theme"
DEFAULT_THEME = "void"   # the look with no folder: tokens.css alone (the site's own is SITE_THEME)


def _themes(static_folder: str) -> set[str]:
    """The themes on disk: every folder of static/site/themes with a theme.css."""
    return {p.parent.name for p in (Path(static_folder) / "site" / "themes").glob("*/theme.css")}


def hidden_themes(static_folder: str) -> set[str]:
    """The themes on disk that sit out of the switcher: those whose folder holds a `hidden` file."""
    return {p.parent.name for p in (Path(static_folder) / "site" / "themes").glob("*/hidden")}


def _has_scene(static_folder: str, theme: str) -> bool:
    return (Path(static_folder) / "site" / "themes" / theme / "scene.js").is_file()


def theme_names(static_folder: str, order: list[str] | tuple = ()) -> list[str]:
    """Every theme, the void included, hidden or not: those named in `order` first, in its order,
    then the rest (the void, then the others by name)."""
    known = [DEFAULT_THEME] + sorted(_themes(static_folder) - {DEFAULT_THEME})
    first = [name for name in dict.fromkeys(order) if name in known]
    return first + [name for name in known if name not in first]


def theme_choices(static_folder: str, current: str, order: list[str] | tuple = ()) -> list[dict]:
    """The switcher's rows (templates/partials/_themes.html), in the order chosen in /admin/settings,
    the hidden ones left out (the current theme stays listed even when hidden, so it reads as chosen)."""
    hidden = hidden_themes(static_folder)
    names = [name for name in theme_names(static_folder, order) if name == current or name not in hidden]
    return [{"name": name, "current": name == current} for name in names]


@lru_cache(maxsize=32)
def _theme_meta(path: str, mtime: float) -> tuple[str | None, str | None]:
    """A theme file's `color-scheme` and `--bg`, for the <head>'s meta tags (None: not set there)."""
    css = Path(path).read_text(encoding="utf-8")
    scheme = re.search(r"color-scheme:\s*(light|dark)", css)
    bg = re.search(r"--bg:\s*(#[0-9a-fA-F]{3,8})", css)
    return (scheme.group(1) if scheme else None, bg.group(1) if bg else None)


def theme_meta(static_folder: str, theme: str) -> dict:
    """The theme's colour scheme and page colour (its theme.css over tokens.css), so the browser's
    own chrome and first paint match the page before the stylesheets arrive."""
    scheme, bg = "dark", "#050505"
    files = [Path(static_folder) / "site" / "tokens.css"]
    if theme != DEFAULT_THEME:
        files.append(Path(static_folder) / "site" / "themes" / theme / "theme.css")
    for file in files:
        try:
            own_scheme, own_bg = _theme_meta(str(file), file.stat().st_mtime)
        except OSError:
            continue
        scheme, bg = own_scheme or scheme, own_bg or bg
    return {"scheme": scheme, "bg": bg}


def _settings() -> dict:
    """The admin's site settings, or none if they cannot be read (a page must still render)."""
    from .site_settings import get_site_settings_store

    if "design_settings" not in g:
        try:
            g.design_settings = get_site_settings_store().get_settings()
        except Exception:
            current_app.logger.exception("Site settings unavailable for the theme")
            g.design_settings = {}
    return g.design_settings


def site_theme(static_folder: str, settings: dict) -> str:
    """The site's own theme: the one chosen in /admin/settings, else SITE_THEME, else the void
    (a name that is no theme on disk is passed over)."""
    known = _themes(static_folder) | {DEFAULT_THEME}
    for candidate in (settings.get("theme_default"), current_app.config.get("SITE_THEME")):
        candidate = (candidate or "").strip()
        if candidate in known:
            return candidate
    return DEFAULT_THEME


def _site_theme() -> str:
    return site_theme(current_app.static_folder, _settings())


def _requested_theme() -> str:
    """The theme for this request: a ?theme= preview, the visitor's kept preview, or the site's."""
    known = _themes(current_app.static_folder)
    for candidate in (request.args.get("theme"), request.cookies.get(THEME_COOKIE)):
        if candidate == DEFAULT_THEME or candidate in known:
            return candidate
    return _site_theme()


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
        settings = _settings()
        return {
            "site_theme": theme,
            "site_theme_css": None if theme == DEFAULT_THEME else url_for("static", filename=f"site/themes/{theme}/theme.css"),
            # The scene's side of the theme (static/home/src/theme.js loads it); None: the scene's own world.
            "site_theme_scene": url_for("static", filename=f"site/themes/{theme}/scene.js") if theme != DEFAULT_THEME and _has_scene(static_folder, theme) else None,
            "site_themes": theme_choices(static_folder, theme, settings.get("theme_order") or ()),
            "site_theme_meta": theme_meta(static_folder, theme),
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
        if chosen == _site_theme():
            response.delete_cookie(THEME_COOKIE)
        elif chosen == DEFAULT_THEME or chosen in _themes(current_app.static_folder):
            response.set_cookie(THEME_COOKIE, chosen, max_age=60 * 60 * 24 * 30, samesite="Lax", httponly=True)
        return response
