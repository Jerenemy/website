"""Share-link attribution: how many people open a shared link, and how many tap through.

Counts only, per UTC day: page views per (kind, source) and call-to-action clicks per
(kind, source, target). Nothing about the visitor is stored: no IP address, no user agent, no
cookie, no identifier. The user agent is read once, to skip link-preview fetchers and crawlers,
and then dropped.

``source`` is the ``?s=`` parameter the app adds to shared links (which surface the link was
shared from); anything unknown counts as "unknown". The store is a SQLite file under instance/,
like the site's other small stores (WTT_DATABASE_PATH, CLASH_ROYALE_DATABASE_PATH). Counting
never breaks a page: a storage error is logged and the request carries on.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app

SOURCES = ("review", "episode", "podcast", "profile", "list", "invite", "story", "recap", "creator")
KINDS = ("review", "episode", "podcast", "profile", "list", "invite", "recap", "creator")
# Pages that aren't app links themselves: their taps on "Open in Sonar" are counted under the
# page's own kind (sent as k=), not under the kind of the share path they open.
PAGE_KINDS = ("creator",)
TARGETS = ("app", "appstore")
UNKNOWN = "unknown"

# Link-preview fetchers and crawlers, matched case-insensitively against the User-Agent.
# iMessage's previews arrive as "facebookexternalhit" + "Twitterbot"; LinkedIn, Skype, Teams and
# most chat apps put "bot/", "preview" or "crawl" in theirs, and crawlers a "+http://" contact link.
# (A bare "bot" would also match phones like the CUBOT in Android user agents.)
BOT_MARKERS = (
    "facebookexternalhit", "facebookcatalog", "meta-externalagent", "twitterbot", "slackbot",
    "slack-imgproxy", "whatsapp", "telegrambot", "discordbot", "applebot", "linkedinbot",
    "skypeuripreview", "microsoftpreview", "pinterest", "redditbot", "embedly", "iframely",
    "googlebot", "google-inspectiontool", "googleother", "bingbot", "bingpreview", "duckduckbot",
    "yandex", "baiduspider", "petalbot", "semrush", "ahrefs", "mj12bot", "dotbot", "bytespider",
    "gptbot", "chatgpt-user", "oai-searchbot", "claudebot", "claude-user", "perplexitybot",
    "amazonbot", "headlesschrome", "python-requests", "curl/", "wget/", "go-http-client",
    "okhttp", "node-fetch", "axios/", "bot/", "bot;", "+http", "crawler", "spider", "preview",
    "scraper",
)


def normalize_source(value):
    value = (value or "").strip().lower()
    return value if value in SOURCES else UNKNOWN


def normalize_kind(value):
    value = (value or "").strip().lower()
    return value if value in KINDS else UNKNOWN


def is_bot(user_agent):
    ua = (user_agent or "").lower()
    if not ua:
        return True
    return any(marker in ua for marker in BOT_MARKERS)


def should_count(request):
    """A real person opening the page: GET, not a prefetch, not a preview fetcher."""
    if request.method != "GET":
        return False
    purpose = (request.headers.get("Sec-Purpose") or request.headers.get("Purpose") or "").lower()
    if "prefetch" in purpose or "prerender" in purpose:
        return False
    return not is_bot(request.headers.get("User-Agent"))


def _today():
    return datetime.now(timezone.utc).date().isoformat()


@contextmanager
def database():
    path = Path(current_app.config["SONAR_STATS_DATABASE_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS sonar_share_views (
                day TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, kind, source)
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS sonar_share_clicks (
                day TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, kind, source, target)
            )""")
            yield connection
    finally:
        connection.close()


def _bump(sql, values):
    try:
        with database() as connection:
            connection.execute(sql, values)
    except (sqlite3.Error, OSError):
        current_app.logger.warning("sonar share attribution: could not record", exc_info=True)


def record_view(kind, source):
    _bump(
        "INSERT INTO sonar_share_views (day, kind, source, count) VALUES (?, ?, ?, 1) "
        "ON CONFLICT(day, kind, source) DO UPDATE SET count = count + 1",
        (_today(), normalize_kind(kind), normalize_source(source)),
    )


def record_click(kind, source, target):
    if target not in TARGETS:
        return
    _bump(
        "INSERT INTO sonar_share_clicks (day, kind, source, target, count) VALUES (?, ?, ?, ?, 1) "
        "ON CONFLICT(day, kind, source, target) DO UPDATE SET count = count + 1",
        (_today(), normalize_kind(kind), normalize_source(source), target),
    )


def summary(days):
    """Rows of kind, source, views, app clicks, App Store clicks and click-through rate for the
    last `days` UTC days (today included), busiest first, plus a totals row."""
    since = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
    table = {}
    try:
        with database() as connection:
            for row in connection.execute(
                "SELECT kind, source, SUM(count) AS n FROM sonar_share_views WHERE day >= ? GROUP BY kind, source",
                (since,),
            ):
                table.setdefault((row["kind"], row["source"]), {"views": 0, "app": 0, "appstore": 0})["views"] = row["n"]
            for row in connection.execute(
                "SELECT kind, source, target, SUM(count) AS n FROM sonar_share_clicks WHERE day >= ? "
                "GROUP BY kind, source, target",
                (since,),
            ):
                entry = table.setdefault((row["kind"], row["source"]), {"views": 0, "app": 0, "appstore": 0})
                entry[row["target"]] = row["n"]
    except (sqlite3.Error, OSError):
        current_app.logger.warning("sonar share attribution: could not read", exc_info=True)
        return None

    rows = [_row(kind, source, **counts) for (kind, source), counts in table.items()]
    rows.sort(key=lambda row: (-row["views"], -row["clicks"], row["kind"], row["source"]))
    totals = _row("All", "", views=sum(r["views"] for r in rows), app=sum(r["app"] for r in rows),
                  appstore=sum(r["appstore"] for r in rows))
    return {"days": days, "since": since, "rows": rows, "totals": totals}


def _row(kind, source, views, app, appstore):
    clicks = app + appstore
    return {
        "kind": kind,
        "source": source,
        "views": views,
        "app": app,
        "appstore": appstore,
        "clicks": clicks,
        "ctr": (clicks / views) if views else None,
    }
