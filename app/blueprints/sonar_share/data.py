"""Read-only lookups for share pages, with a small in-process TTL cache."""

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from flask import current_app

TIMEOUT = 4
CACHE_TTL = 600
_cache: dict = {}

UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
NUMERIC_RE = re.compile(r"^[0-9]{1,20}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{1,30}$")


@dataclass
class Podcast:
    id: str
    name: str
    author: str = ""
    artwork: Optional[str] = None
    description: str = ""


@dataclass
class Episode:
    id: str
    title: str
    artwork: Optional[str] = None
    podcast: Optional[Podcast] = None


@dataclass
class Review:
    id: str
    username: Optional[str]
    rating: Optional[int]  # 1...10
    is_loved: bool
    text: Optional[str]
    episode: Optional[Episode]


@dataclass
class Profile:
    username: str
    logged_count: Optional[int] = None


def _cached(key, loader):
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        value = loader()
    except Exception:  # A failed lookup degrades to a generic page.
        current_app.logger.warning("sonar share lookup failed: %s", key, exc_info=True)
        value = None
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (now, value)
    return value


# --- Supabase (anon key, public rows only) -------------------------------------------------

def _supabase(path, params, headers=None):
    url = current_app.config.get("SONAR_SUPABASE_URL")
    key = current_app.config.get("SONAR_SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    response = requests.get(
        f"{url.rstrip('/')}/rest/v1/{path}",
        params=params,
        headers={"apikey": key, "Authorization": f"Bearer {key}", **(headers or {})},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response


# --- Podcast Index -------------------------------------------------------------------------

def _podcast_index(path, params):
    key = current_app.config.get("PODCASTINDEX_API_KEY")
    secret = current_app.config.get("PODCASTINDEX_API_SECRET")
    if not key or not secret:
        return None
    now = str(int(time.time()))
    digest = hashlib.sha1((key + secret + now).encode()).hexdigest()
    response = requests.get(
        f"https://api.podcastindex.org/api/1.0/{path}",
        params=params,
        headers={
            "X-Auth-Key": key,
            "X-Auth-Date": now,
            "Authorization": digest,
            "User-Agent": "SonarShare/1.0 (jeremyzay.com)",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _artwork(item):
    for field in ("artwork", "image", "feedImage"):
        value = (item or {}).get(field)
        if value:
            return value
    return None


def podcast(podcast_id: str) -> Optional[Podcast]:
    if not NUMERIC_RE.match(podcast_id or ""):
        return None

    def load():
        data = _podcast_index("podcasts/byfeedid", {"id": podcast_id})
        feed = (data or {}).get("feed")
        if not feed or not feed.get("title"):
            return None
        return Podcast(
            id=podcast_id,
            name=feed["title"].strip(),
            author=(feed.get("author") or feed.get("ownerName") or "").strip(),
            artwork=_artwork(feed),
            description=_plain(feed.get("description") or ""),
        )

    return _cached(("podcast", podcast_id), load)


def episode(episode_id: str, podcast_id: Optional[str] = None) -> Optional[Episode]:
    if not NUMERIC_RE.match(episode_id or ""):
        return None

    def load():
        data = _podcast_index("episodes/byid", {"id": episode_id})
        item = (data or {}).get("episode")
        if not item or not item.get("title"):
            return None
        show = podcast(str(item.get("feedId") or podcast_id or ""))
        return Episode(
            id=episode_id,
            title=item["title"].strip(),
            artwork=_artwork(item) or (show.artwork if show else None),
            podcast=show,
        )

    return _cached(("episode", episode_id), load)


def review(log_id: str) -> Optional[Review]:
    if not UUID_RE.match(log_id or ""):
        return None

    def load():
        response = _supabase(
            "episode_logs",
            {"id": f"eq.{log_id}", "select": "id,user_id,episode_id,podcast_id,rating,review,is_loved", "limit": 1},
        )
        rows = response.json() if response is not None else []
        if not rows:
            return None
        row = rows[0]
        username = None
        if row.get("user_id"):
            profile_rows = _supabase("profiles", {"id": f"eq.{row['user_id']}", "select": "username", "limit": 1})
            if profile_rows is not None and profile_rows.json():
                username = profile_rows.json()[0].get("username")
        rating = row.get("rating") or None
        text = (row.get("review") or "").strip() or None
        return Review(
            id=log_id,
            username=username,
            rating=rating if rating and rating > 0 else None,
            is_loved=bool(row.get("is_loved")),
            text=text,
            episode=episode(str(row.get("episode_id") or ""), str(row.get("podcast_id") or "")),
        )

    return _cached(("review", log_id), load)


def community_average(episode_id: str) -> Optional[float]:
    """Average rating on the 0...5 scale, or None when nobody has rated it."""
    if not NUMERIC_RE.match(episode_id or ""):
        return None

    def load():
        response = _supabase(
            "episode_logs",
            {"episode_id": f"eq.{episode_id}", "rating": "gt.0", "select": "rating", "limit": 1000},
        )
        ratings = [row["rating"] for row in (response.json() if response is not None else []) if row.get("rating")]
        return round(sum(ratings) / len(ratings) / 2, 1) if ratings else None

    return _cached(("average", episode_id), load)


def profile(username: str) -> Optional[Profile]:
    if not USERNAME_RE.match(username or ""):
        return None

    def load():
        escaped = username.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        response = _supabase("profiles", {"username": f"ilike.{escaped}", "select": "id,username", "limit": 1})
        rows = response.json() if response is not None else []
        if not rows:
            return None
        count = None
        counted = _supabase(
            "episode_logs",
            {"user_id": f"eq.{rows[0]['id']}", "select": "id", "limit": 1},
            headers={"Prefer": "count=exact"},
        )
        if counted is not None:
            total = counted.headers.get("Content-Range", "").split("/")[-1]
            count = int(total) if total.isdigit() else None
        return Profile(username=rows[0]["username"], logged_count=count)

    return _cached(("profile", username.lower()), load)


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _plain(html: str) -> str:
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()
