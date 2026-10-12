"""Read-only lookups for share pages, with a small in-process TTL cache."""

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
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


@dataclass
class ListItem:
    kind: str  # "episode" or "podcast"
    podcast_id: str
    episode_id: Optional[str] = None
    note: Optional[str] = None
    episode: Optional[Episode] = None
    podcast: Optional[Podcast] = None

    @property
    def title(self) -> Optional[str]:
        if self.kind == "episode":
            return self.episode.title if self.episode else None
        return self.podcast.name if self.podcast else None

    @property
    def subtitle(self) -> Optional[str]:
        if self.kind == "episode":
            show = self.episode.podcast if self.episode else None
            return show.name if show else None
        return self.podcast.author if self.podcast else None

    @property
    def artwork(self) -> Optional[str]:
        if self.kind == "episode":
            return self.episode.artwork if self.episode else None
        return self.podcast.artwork if self.podcast else None

    @property
    def path(self) -> str:
        if self.kind == "episode":
            return f"/sonar/e/{self.podcast_id}/{self.episode_id}"
        return f"/sonar/p/{self.podcast_id}"


@dataclass
class SonarList:
    id: str
    title: str
    description: Optional[str] = None
    username: Optional[str] = None
    item_count: int = 0
    items: list = field(default_factory=list)  # the first LIST_PREVIEW_ITEMS ListItems


LIST_PREVIEW_ITEMS = 12


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


def sonar_list(list_id: str) -> Optional[SonarList]:
    """A public list with its first items, or None when it is private, missing or unreadable.

    Only rows the anon key may read come back (RLS decides); ``is_public=eq.true`` is asked
    for explicitly as well, so a private list never renders even if a policy is too wide.
    """
    if not UUID_RE.match(list_id or ""):
        return None

    def load():
        response = _supabase(
            "lists",
            {"id": f"eq.{list_id}", "is_public": "eq.true", "select": "id,user_id,title,description", "limit": 1},
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
        items_response = _supabase(
            "list_items",
            {
                "list_id": f"eq.{list_id}",
                "select": "kind,podcast_id,episode_id,note",
                "order": "position.asc,added_at.asc",
                "limit": LIST_PREVIEW_ITEMS,
            },
            headers={"Prefer": "count=exact"},
        )
        item_rows = items_response.json() if items_response is not None else []
        total = items_response.headers.get("Content-Range", "").split("/")[-1] if items_response is not None else ""
        items = [
            ListItem(
                kind=item.get("kind"),
                podcast_id=str(item.get("podcast_id") or ""),
                episode_id=str(item["episode_id"]) if item.get("episode_id") else None,
                note=(item.get("note") or "").strip() or None,
            )
            for item in item_rows
            if item.get("kind") in ("episode", "podcast") and NUMERIC_RE.match(str(item.get("podcast_id") or ""))
            and (item.get("kind") == "podcast" or NUMERIC_RE.match(str(item.get("episode_id") or "")))
        ]
        _resolve_items(items)
        return SonarList(
            id=list_id,
            title=(row.get("title") or "").strip() or "A list",
            description=(row.get("description") or "").strip() or None,
            username=username,
            item_count=int(total) if total.isdigit() else len(item_rows),
            items=items,
        )

    return _cached(("list", list_id.lower()), load)


def _resolve_items(items):
    """Fills in titles and artwork from Podcast Index, a few lookups at a time."""
    if not items:
        return
    app = current_app._get_current_object()

    def resolve(item):
        with app.app_context():
            if item.kind == "episode":
                item.episode = episode(item.episode_id, item.podcast_id)
            else:
                item.podcast = podcast(item.podcast_id)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(resolve, items))


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _plain(html: str) -> str:
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()
