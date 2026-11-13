"""Sonar's website moved to sonar.show (the sonar repo, site/). What stays here is what old links
and released apps need: redirects from /sonar, and the apple-app-site-association file, which must
keep answering on this host with the old paths so those apps still open their links. /admin/sonar
reads the share counts from the Sonar site over localhost, the way /admin/jobs reads the job bot.
"""
import requests
from flask import Blueprint, current_app, jsonify, redirect, render_template, request

from ..admin.routes import _csrf_token, admin_required

bp = Blueprint("sonar_share", __name__)

SONAR_ORIGIN = "https://sonar.show"
TEAM_ID = "9A9HR6WT4K"
BUNDLE_ID = "com.jeremyzay.Sonar"
SHARE_PATHS = ("/sonar/r/*", "/sonar/e/*", "/sonar/p/*", "/sonar/u/*", "/sonar/l/*", "/sonar/i/*")
# Blink: its links open the app when installed, and its App Clip otherwise.
BLINK_APP = f"{TEAM_ID}.com.jeremyzay.blink"
BLINK_CLIP = f"{TEAM_ID}.com.jeremyzay.blink.Clip"


@bp.get("/.well-known/apple-app-site-association")
@bp.get("/apple-app-site-association")
def apple_app_site_association():
    """Lets iOS open Sonar's share links in the app. Served as JSON, never redirected."""
    response = jsonify(
        {
            "applinks": {
                "details": [
                    {
                        "appIDs": [f"{TEAM_ID}.{BUNDLE_ID}"],
                        "components": [{"/": path} for path in SHARE_PATHS],
                    },
                    {
                        "appIDs": [BLINK_APP],
                        "components": [{"/": "/blink/v*"}],
                    },
                ]
            },
            "appclips": {"apps": [BLINK_CLIP]},
        }
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@bp.get("/sonar", strict_slashes=False, defaults={"path": ""})
@bp.get("/sonar/<path:path>")
def moved(path):
    query = request.query_string.decode("latin-1")
    return redirect(f"{SONAR_ORIGIN}/{path}" + (f"?{query}" if query else ""), code=301)


def _share_stats():
    """{"periods": [...], "sources": [...]} from the Sonar site, or None when it can't be read."""
    try:
        response = requests.get(
            f"{current_app.config['SONAR_SITE_URL']}/internal/stats",
            headers={"Authorization": f"Bearer {current_app.config.get('SONAR_STATS_TOKEN') or ''}"},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        current_app.logger.exception("Could not read Sonar's share stats")
        return None


@bp.get("/admin/sonar")
@admin_required
def share_stats():
    stats = _share_stats() or {"periods": [None, None], "sources": []}
    response = current_app.make_response(render_template(
        "admin/sonar_stats.html",
        periods=stats["periods"],
        sources=stats["sources"],
        csrf_token=_csrf_token(),
    ))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
