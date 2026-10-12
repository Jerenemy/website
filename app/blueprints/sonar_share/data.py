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

UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}\Z")
# A log the app counts as "logged": anything but a bare listen-later save
# (LogDisplayHelpers.isListenLaterOnly in the app).
LOGGED_FILTER = "(listen_later.is.null,listen_later.is.false,is_listened.is.true,rating.gt.0,is_loved.is.true,review.not.is.null)"
# A log with something to show: a rating or written words.
REVIEWED_FILTER = "(rating.gt.0,and(review.not.is.null,review.neq.))"
REVIEW_COLUMNS = (
    "id,user_id,episode_id,podcast_id,rating,review,is_loved,created_at,review_like_count,review_reply_count"
)
NUMERIC_RE = re.compile(r"^[0-9]{1,20}\Z")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{1,30}\Z")


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
    user_id: Optional[str] = None
    like_count: Optional[int] = None   # None: not readable
    reply_count: Optional[int] = None
    created_at: Optional[str] = None
    episode_id: Optional[str] = None
    podcast_id: Optional[str] = None

    @property
    def path(self) -> str:
        return f"/sonar/r/{self.id}"


@dataclass
class Profile:
    username: str
    logged_count: Optional[int] = None
    id: Optional[str] = None


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
            {"id": f"eq.{log_id}", "select": REVIEW_COLUMNS, "limit": 1},
        )
        rows = response.json() if response is not None else []
        if not rows:
            return None
        row = rows[0]
        usernames = _usernames([row.get("user_id")])
        item = _review_from_row(row, usernames)
        item.episode = episode(item.episode_id or "", item.podcast_id or "")
        return item

    return _cached(("review", log_id), load)


def community_rating(episode_id: str):
    """(average on the 0...5 scale, number of ratings), or (None, 0) when nobody has rated it."""
    if not NUMERIC_RE.match(episode_id or ""):
        return None, 0

    def load():
        response = _supabase(
            "episode_logs",
            {"episode_id": f"eq.{episode_id}", "rating": "gt.0", "select": "rating", "limit": 1000},
        )
        ratings = [row["rating"] for row in (response.json() if response is not None else []) if row.get("rating")]
        return (round(sum(ratings) / len(ratings) / 2, 1), len(ratings)) if ratings else (None, 0)

    return _cached(("average", episode_id), load) or (None, 0)


def community_average(episode_id: str) -> Optional[float]:
    """Average rating on the 0...5 scale, or None when nobody has rated it."""
    return community_rating(episode_id)[0]


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
            {"user_id": f"eq.{rows[0]['id']}", "or": LOGGED_FILTER, "select": "id", "limit": 1},
            headers={"Prefer": "count=exact"},
        )
        if counted is not None:
            total = counted.headers.get("Content-Range", "").split("/")[-1]
            count = int(total) if total.isdigit() else None
        return Profile(username=rows[0]["username"], logged_count=count, id=rows[0].get("id"))

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


# --- Richer pages: profile sections, more reviews -------------------------------------------
#
# Every section is read with the anon key, so RLS decides what exists here. A section the anon
# role can't read (permission denied, or a missing table) comes back as None and the page hides
# it; a readable but empty section is an empty list. See the PR for which sections are blocked.

PROFILE_RECENT_REVIEWS = 5
PROFILE_LISTS = 6
MORE_REVIEWS = 3
EPISODE_TOP_REVIEWS = 5


@dataclass
class ListSummary:
    id: str
    title: str
    item_count: Optional[int] = None

    @property
    def path(self) -> str:
        return f"/sonar/l/{self.id}"


@dataclass
class ProfilePage:
    profile: Profile
    avatar_url: Optional[str] = None
    followers: Optional[int] = None       # None: hidden (unreadable, or nothing to show)
    following: Optional[int] = None
    favorites: Optional[list] = None      # ListItems; None: unreadable
    recent_reviews: Optional[list] = None  # Reviews
    lists: Optional[list] = None          # ListSummaries

    @property
    def username(self) -> str:
        return self.profile.username

    @property
    def artwork(self) -> list:
        """Distinct artwork URLs from favourites, then recent reviews (for the invite card)."""
        urls = [item.artwork for item in self.favorites or []]
        urls += [item.episode.artwork for item in self.recent_reviews or [] if item.episode]
        return list(dict.fromkeys(url for url in urls if url))


def _optional(path, params, headers=None):
    """Like _supabase, but a refused or failed read is None instead of an error."""
    try:
        return _supabase(path, params, headers)
    except requests.RequestException as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        current_app.logger.info("sonar share: %s not readable (%s)", path, status or error)
        return None


def _rows(response):
    if response is None:
        return None
    rows = response.json()
    return rows if isinstance(rows, list) else None


def _total(response):
    if response is None:
        return None
    total = response.headers.get("Content-Range", "").split("/")[-1]
    return int(total) if total.isdigit() else None


def _parallel(functions):
    """Runs zero-argument callables a few at a time inside the app context; returns their results."""
    if not functions:
        return []
    app = current_app._get_current_object()

    def run(function):
        with app.app_context():
            return function()

    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(run, functions))


def _usernames(user_ids) -> dict:
    ids = sorted({str(user_id) for user_id in user_ids if user_id and UUID_RE.match(str(user_id))})
    if not ids:
        return {}
    rows = _rows(_optional("profiles", {"id": f"in.({','.join(ids)})", "select": "id,username", "limit": len(ids)}))
    return {row["id"]: row.get("username") for row in rows or [] if row.get("id")}


def _count(value):
    return value if isinstance(value, int) and value >= 0 else None


def _review_from_row(row, usernames) -> Review:
    rating = row.get("rating") or None
    return Review(
        id=str(row.get("id")),
        username=usernames.get(row.get("user_id")),
        rating=rating if rating and rating > 0 else None,
        is_loved=bool(row.get("is_loved")),
        text=(row.get("review") or "").strip() or None,
        episode=None,
        user_id=row.get("user_id"),
        like_count=_count(row.get("review_like_count")),
        reply_count=_count(row.get("review_reply_count")),
        created_at=row.get("created_at"),
        episode_id=str(row.get("episode_id") or "") or None,
        podcast_id=str(row.get("podcast_id") or "") or None,
    )


def _reviews(rows, usernames=None, resolve=True) -> list:
    rows = [row for row in rows or [] if row.get("id") and UUID_RE.match(str(row["id"]))]
    usernames = usernames if usernames is not None else _usernames(row.get("user_id") for row in rows)
    items = [_review_from_row(row, usernames) for row in rows]
    if resolve:
        episodes = _parallel([
            (lambda item=item: episode(item.episode_id or "", item.podcast_id or "")) for item in items
        ])
        for item, resolved in zip(items, episodes):
            item.episode = resolved
    return items


def more_reviews(review_item: Review, limit: int = MORE_REVIEWS) -> list:
    """A few other reviews by the same person, newest first."""
    user_id = review_item.user_id
    if not user_id or not UUID_RE.match(str(user_id)):
        return []

    def load():
        rows = _rows(_optional("episode_logs", {
            "user_id": f"eq.{user_id}",
            "id": f"neq.{review_item.id}",
            "or": REVIEWED_FILTER,
            "select": REVIEW_COLUMNS,
            "order": "created_at.desc",
            "limit": limit,
        }))
        return _reviews(rows, {user_id: review_item.username})

    return _cached(("more", str(review_item.id).lower(), limit), load) or []


def episode_reviews(episode_id: str, limit: int = EPISODE_TOP_REVIEWS) -> list:
    """The community's written reviews of an episode: most liked first, then newest."""
    if not NUMERIC_RE.match(episode_id or ""):
        return []

    def load():
        rows = _rows(_optional("episode_logs", {
            "episode_id": f"eq.{episode_id}",
            "and": "(review.not.is.null,review.neq.)",
            "select": REVIEW_COLUMNS,
            "order": "review_like_count.desc.nullslast,created_at.desc",
            "limit": limit * 2,
        }))
        items = [item for item in _reviews(rows, resolve=False) if item.text][:limit]
        return items

    return _cached(("episode_reviews", episode_id, limit), load) or []


def avatar_url(user_id: str) -> Optional[str]:
    """The public URL of a user's photo, when profile_details is readable and they have one."""
    base = current_app.config.get("SONAR_SUPABASE_URL")
    if not base or not user_id or not UUID_RE.match(str(user_id)):
        return None
    rows = _rows(_optional("profile_details", {
        "user_id": f"eq.{user_id}", "select": "avatar_path,avatar_updated_at", "limit": 1,
    }))
    if not rows or not rows[0].get("avatar_path"):
        return None
    path = rows[0]["avatar_path"]
    if path != f"{str(user_id).lower()}/avatar.jpg":  # the table's own check; never trust more
        return None
    version = re.sub(r"[^0-9A-Za-z]", "", str(rows[0].get("avatar_updated_at") or ""))[:32]
    url = f"{base.rstrip('/')}/storage/v1/object/public/avatars/{path}"
    return f"{url}?v={version}" if version else url


def _favorites(user_id) -> Optional[list]:
    rows = _rows(_optional("profile_favorites", {
        "user_id": f"eq.{user_id}", "select": "kind,podcast_id,episode_id", "order": "position.asc", "limit": 4,
    }))
    if rows is None:
        return None
    items = [
        ListItem(kind=row.get("kind"), podcast_id=str(row.get("podcast_id") or ""),
                 episode_id=str(row["episode_id"]) if row.get("episode_id") else None)
        for row in rows
        if row.get("kind") in ("episode", "podcast") and NUMERIC_RE.match(str(row.get("podcast_id") or ""))
        and (row.get("kind") == "podcast" or NUMERIC_RE.match(str(row.get("episode_id") or "")))
    ]
    _resolve_items(items)
    return items


def _recent_reviews(user_id, username) -> Optional[list]:
    rows = _rows(_optional("episode_logs", {
        "user_id": f"eq.{user_id}",
        "or": REVIEWED_FILTER,
        "select": REVIEW_COLUMNS,
        "order": "created_at.desc",
        "limit": PROFILE_RECENT_REVIEWS,
    }))
    return None if rows is None else _reviews(rows, {user_id: username})


def _public_lists(user_id) -> Optional[list]:
    rows = _rows(_optional("lists", {
        "user_id": f"eq.{user_id}",
        "is_public": "eq.true",
        "select": "id,title,list_items(count)",
        "order": "updated_at.desc",
        "limit": PROFILE_LISTS,
    }))
    if rows is None:
        return None
    summaries = []
    for row in rows:
        if not UUID_RE.match(str(row.get("id") or "")):
            continue
        counts = row.get("list_items") or []
        count = counts[0].get("count") if counts and isinstance(counts[0], dict) else None
        summaries.append(ListSummary(id=row["id"], title=(row.get("title") or "").strip() or "A list",
                                     item_count=_count(count)))
    return summaries


def _follow_count(column, user_id) -> Optional[int]:
    return _total(_optional(
        "user_follows",
        {column: f"eq.{user_id}", "select": "follower_id", "limit": 1},
        headers={"Prefer": "count=exact"},
    ))


def profile_page(username: str) -> Optional[ProfilePage]:
    """A profile with every section the anon key can read, or None for an unknown user."""
    base = profile(username)
    if base is None or not base.id:
        return None

    def load():
        user_id = base.id
        avatar, followers, following, favorites, recent, lists = _parallel([
            lambda: avatar_url(user_id),
            lambda: _follow_count("following_id", user_id),
            lambda: _follow_count("follower_id", user_id),
            lambda: _favorites(user_id),
            lambda: _recent_reviews(user_id, base.username),
            lambda: _public_lists(user_id),
        ])
        if not followers and not following:
            # Zero on both sides can also be RLS quietly returning no rows: show nothing
            # rather than a possibly wrong "0 followers".
            followers = following = None
        return ProfilePage(profile=base, avatar_url=avatar, followers=followers, following=following,
                           favorites=favorites, recent_reviews=recent, lists=lists)

    return _cached(("profile_page", username.lower()), load)


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _plain(html: str) -> str:
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()
