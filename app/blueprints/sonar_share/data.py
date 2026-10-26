"""Read-only lookups for share pages, with a small in-process TTL cache."""

import datetime as dt
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
    avatar_url: Optional[str] = None  # the author's photo, where the page shows the author
    badge: Optional[str] = None       # the badge beside the author's name (name_badge)

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
    user_id: Optional[str] = None
    avatar_url: Optional[str] = None  # the owner's photo
    badge: Optional[str] = None       # the badge beside the owner's name


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
        _add_people([item])
        return item

    return _cached(("review", log_id), load)


def community_rating(episode_id: str):
    """(average on the 0...5 scale, number of ratings), or (None, 0) when nobody has rated it."""
    return episode_rating(episode_id) or (None, 0)


def episode_rating(episode_id: str):
    """Like community_rating, but None when the lookup failed (so a badge can cache it briefly)."""
    if not NUMERIC_RE.match(episode_id or ""):
        return None, 0

    def load():
        response = _supabase(
            "episode_logs",
            {"episode_id": f"eq.{episode_id}", "rating": "gt.0", "select": "rating", "limit": 1000},
        )
        ratings = [row["rating"] for row in (response.json() if response is not None else []) if row.get("rating")]
        return (round(sum(ratings) / len(ratings) / 2, 1), len(ratings)) if ratings else (None, 0)

    return _cached(("average", episode_id), load)


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
        result = SonarList(
            id=list_id,
            title=(row.get("title") or "").strip() or "A list",
            description=(row.get("description") or "").strip() or None,
            username=username,
            item_count=int(total) if total.isdigit() else len(item_rows),
            items=items,
            user_id=row.get("user_id"),
        )
        _add_people([result])
        return result

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
    badges: list = field(default_factory=list)         # BADGE_KINDS they have, in order
    creator_shows: list = field(default_factory=list)  # Podcasts they make, for "Makes <show>"

    @property
    def username(self) -> str:
        return self.profile.username

    @property
    def name_badge(self) -> Optional[str]:
        return name_badge(self.badges)

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


def _user_ids(user_ids) -> list:
    """Distinct, well-formed user ids, sorted (so a set of people caches under one key)."""
    return sorted({str(user_id) for user_id in user_ids if user_id and UUID_RE.match(str(user_id))})


def _usernames(user_ids) -> dict:
    ids = _user_ids(user_ids)
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
        _add_people(items)
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
    return _photo_url(base, user_id, rows[0]) if rows else None


def avatar_urls(user_ids) -> dict:
    """Photo URLs by user id for the people on one page (an episode's reviewers): one read."""
    base = current_app.config.get("SONAR_SUPABASE_URL")
    ids = _user_ids(user_ids)
    if not base or not ids:
        return {}
    rows = _rows(_optional("profile_details", {
        "user_id": f"in.({','.join(ids)})", "select": "user_id,avatar_path,avatar_updated_at", "limit": len(ids),
    }))
    photos = {}
    for row in rows or []:
        url = _photo_url(base, row.get("user_id"), row) if row.get("user_id") in ids else None
        if url:
            photos[row["user_id"]] = url
    return photos


def _photo_url(base, user_id, row) -> Optional[str]:
    path = row.get("avatar_path")
    if not path or path != f"{str(user_id).lower()}/avatar.jpg":  # the table's own check; never trust more
        return None
    version = re.sub(r"[^0-9A-Za-z]", "", str(row.get("avatar_updated_at") or ""))[:32]
    url = f"{base.rstrip('/')}/storage/v1/object/public/avatars/{path}"
    return f"{url}?v={version}" if version else url


# --- Badges --------------------------------------------------------------------------------
#
# The marks the app shows for a person (ProfileBadgeKind in Sonar/Models/ProfileBadge.swift):
# every badge under the name on a profile, and one of them beside the name everywhere else.
# The anon key can read them once Sonar's 20261114_public_badges_web_read.sql is applied;
# before that nobody has any here and the pages look as they did.

BADGE_KINDS = ("founder", "core_designer", "creator", "tester", "early_adopter")  # the app's order
# Worth a glyph beside a name. Tester and Early adopter stay on the profile, so the mark keeps
# meaning something.
NAME_BADGES = ("founder", "core_designer", "creator")
# Titles and what each means, word for word from the app.
BADGE_TITLES = {
    "founder": "Founder",
    "core_designer": "Core Designer",
    "creator": "Creator",
    "tester": "Tester",
    "early_adopter": "Early adopter",
}
BADGE_EXPLANATIONS = {
    "founder": "Built Sonar.",
    "core_designer": "Shapes how Sonar looks and feels.",
    "creator": "Makes a show on Sonar, confirmed through the show's own feed.",
    "tester": "Helped test Sonar before release.",
    "early_adopter": "Joined Sonar before 2027 and helped shape it.",
}
CREATOR_SHOW_LINKS = 3


def badges(user_ids) -> dict:
    """Badges by user id, in the app's order. People without any are left out."""
    ids = _user_ids(user_ids)
    if not ids:
        return {}

    def load():
        rows = _rows(_optional("profile_badges", {
            "user_id": f"in.({','.join(ids)})", "select": "user_id,kind", "limit": len(ids) * len(BADGE_KINDS),
        }))
        found = {}
        for row in rows or []:
            if row.get("user_id") in ids and row.get("kind") in BADGE_KINDS:
                found.setdefault(row["user_id"], set()).add(row["kind"])
        return {user_id: [kind for kind in BADGE_KINDS if kind in kinds] for user_id, kinds in found.items()}

    return _cached(("badges", *ids), load) or {}


def name_badge(kinds) -> Optional[str]:
    """The one badge shown beside a name: Founder, else Core Designer, else Creator."""
    return next((kind for kind in NAME_BADGES if kind in (kinds or ())), None)


def creator_shows(user_id) -> list:
    """The shows a creator proved are theirs, oldest first, as on their profile in the app."""
    if not user_id or not UUID_RE.match(str(user_id)):
        return []
    rows = _rows(_optional("creator_shows", {
        "user_id": f"eq.{user_id}", "select": "podcast_id", "order": "verified_at.asc", "limit": CREATOR_SHOW_LINKS,
    }))
    ids = [str(row["podcast_id"]) for row in rows or [] if NUMERIC_RE.match(str(row.get("podcast_id") or ""))]
    return [show for show in _parallel([(lambda pid=pid: podcast(pid)) for pid in ids]) if show]


def _add_people(items):
    """Fills in each item's author photo and name badge (reviews, a list): two reads for all."""
    ids = [item.user_id for item in items if item.user_id]
    if not ids:
        return
    photos, kinds = _parallel([lambda: avatar_urls(ids), lambda: badges(ids)])
    for item in items:
        item.avatar_url = photos.get(item.user_id)
        item.badge = name_badge(kinds.get(item.user_id))


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
        avatar, followers, following, favorites, recent, lists, kinds = _parallel([
            lambda: avatar_url(user_id),
            lambda: _follow_count("following_id", user_id),
            lambda: _follow_count("follower_id", user_id),
            lambda: _favorites(user_id),
            lambda: _recent_reviews(user_id, base.username),
            lambda: _public_lists(user_id),
            lambda: badges([user_id]).get(user_id, []),
        ])
        if not followers and not following:
            # Zero on both sides can also be RLS quietly returning no rows: show nothing
            # rather than a possibly wrong "0 followers".
            followers = following = None
        return ProfilePage(profile=base, avatar_url=avatar, followers=followers, following=following,
                           favorites=favorites, recent_reviews=recent, lists=lists, badges=kinds,
                           creator_shows=creator_shows(user_id) if "creator" in kinds else [])

    return _cached(("profile_page", username.lower()), load)


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _plain(html: str) -> str:
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()


# --- Creators: a show's ratings on Sonar ----------------------------------------------------
#
# Everything here comes from episode_logs, which the anon key may read (select using (true)).
# Reads are bounded: at most CREATOR_MAX_ROWS logs per show. Past that, the totals still come
# from PostgREST's exact count, and the averages from the most recent CREATOR_MAX_ROWS logs.

CREATOR_MAX_ROWS = 5000
CREATOR_TOP_EPISODES = 5
CREATOR_TOP_REVIEWS = 4
SEARCH_RESULTS = 6

APPLE_PODCASTS_RE = re.compile(
    r"^(?:https?://)?(?:podcasts|itunes)\.apple\.com/(?:[^?#]*/)?id([0-9]{1,15})(?:[/?#].*)?\Z", re.IGNORECASE
)
SONAR_LINK_RE = re.compile(
    r"^(?:(?:https?://)?(?:www\.)?jeremyzay\.com)?/sonar/(?:creators/)?(?:p|e)/([0-9]{1,20})(?:/[0-9]{1,20})?/?(?:[?#].*)?\Z"
    r"|^sonar://(?:podcast|episode)/([0-9]{1,20})(?:/[0-9]{1,20})?\Z",
    re.IGNORECASE,
)


@dataclass
class EpisodeStat:
    episode_id: str
    average: float  # 0...5
    count: int
    episode: Optional[Episode] = None


@dataclass
class CreatorStats:
    podcast_id: str
    logs: int = 0           # logged episodes (not bare listen-later saves)
    ratings: int = 0
    average: Optional[float] = None  # 0...5
    reviews: int = 0        # logs with written words
    top_episodes: list = field(default_factory=list)  # EpisodeStats, best first
    top_reviews: list = field(default_factory=list)   # Reviews
    sampled: bool = False   # more logs than CREATOR_MAX_ROWS: averages come from the newest ones


def _average(points):
    """Average of 1...10 ratings on the 0...5 scale, one decimal."""
    return round(sum(points) / len(points) / 2, 1) if points else None


def podcast_rating(podcast_id: str):
    """(average on the 0...5 scale, number of ratings) across a show's episodes; (None, 0) when
    nobody has rated it; None when the lookup failed."""
    if not NUMERIC_RE.match(podcast_id or ""):
        return None, 0

    def load():
        response = _supabase(
            "episode_logs",
            {"podcast_id": f"eq.{podcast_id}", "rating": "gt.0", "select": "rating",
             "order": "created_at.desc", "limit": CREATOR_MAX_ROWS},
            headers={"Prefer": "count=exact"},
        )
        rows = _rows(response) or []
        ratings = [row["rating"] for row in rows if isinstance(row.get("rating"), int) and 0 < row["rating"] <= 10]
        count = _total(response)
        return (_average(ratings), max(count or 0, len(ratings))) if ratings else (None, 0)

    return _cached(("podcast_rating", podcast_id), load)


def summarize_show(rows, top=CREATOR_TOP_EPISODES):
    """(ratings, average, reviews, top EpisodeStats) from a show's log rows. Pure, for tests.

    Episodes rank by average, then by how many people rated them; an episode needs two ratings
    to rank while any episode has two (one five-dot log shouldn't top a show's chart)."""
    per_episode = {}
    ratings, reviews = [], 0
    for row in rows or []:
        rating = row.get("rating")
        if (row.get("review") or "").strip():
            reviews += 1
        if not isinstance(rating, int) or not 0 < rating <= 10:
            continue
        ratings.append(rating)
        episode_id = str(row.get("episode_id") or "")
        if NUMERIC_RE.match(episode_id):
            per_episode.setdefault(episode_id, []).append(rating)
    stats = [EpisodeStat(episode_id=k, average=_average(v), count=len(v)) for k, v in per_episode.items()]
    floor = 2 if any(stat.count >= 2 for stat in stats) else 1
    ranked = sorted((stat for stat in stats if stat.count >= floor), key=lambda st: (-st.average, -st.count, st.episode_id))
    return len(ratings), _average(ratings), reviews, ranked[:top]


def creator_stats(podcast_id: str) -> Optional[CreatorStats]:
    """A show's Sonar numbers for its creator page, or None when the lookup failed."""
    if not NUMERIC_RE.match(podcast_id or ""):
        return None

    def load():
        response = _supabase(
            "episode_logs",
            {"podcast_id": f"eq.{podcast_id}", "or": LOGGED_FILTER, "select": "episode_id,rating,review",
             "order": "created_at.desc", "limit": CREATOR_MAX_ROWS},
            headers={"Prefer": "count=exact"},
        )
        rows = _rows(response) or []
        logs = _total(response)
        logs = max(logs or 0, len(rows))
        ratings, average, reviews, top = summarize_show(rows)
        review_rows = _rows(_optional("episode_logs", {
            "podcast_id": f"eq.{podcast_id}",
            "and": "(review.not.is.null,review.neq.)",
            "select": REVIEW_COLUMNS,
            "order": "review_like_count.desc.nullslast,created_at.desc",
            "limit": CREATOR_TOP_REVIEWS * 2,
        }))
        top_reviews = [item for item in _reviews(review_rows, resolve=False) if item.text][:CREATOR_TOP_REVIEWS]
        wanted = list(dict.fromkeys([stat.episode_id for stat in top] + [r.episode_id for r in top_reviews if r.episode_id]))
        resolved = dict(zip(wanted, _parallel([(lambda e=e: episode(e, podcast_id)) for e in wanted])))
        for stat in top:
            stat.episode = resolved.get(stat.episode_id)
        for item in top_reviews:
            item.episode = resolved.get(item.episode_id)
        return CreatorStats(podcast_id=podcast_id, logs=logs, ratings=ratings, average=average, reviews=reviews,
                            top_episodes=top, top_reviews=top_reviews, sampled=len(rows) < logs)

    return _cached(("creator", podcast_id), load)


def podcast_id_from_apple(apple_id: str) -> Optional[str]:
    """The Podcast Index feed id for an Apple Podcasts id, or None."""
    if not NUMERIC_RE.match(apple_id or ""):
        return None

    def load():
        feed = (_podcast_index("podcasts/byitunesid", {"id": apple_id}) or {}).get("feed")
        feed_id = str((feed or {}).get("id") or "") if isinstance(feed, dict) else ""
        return feed_id if NUMERIC_RE.match(feed_id) else None

    return _cached(("itunes", apple_id), load)


def search_podcasts(term: str) -> Optional[list]:
    """Up to SEARCH_RESULTS shows matching `term` on Podcast Index; None when search isn't available."""
    term = " ".join((term or "").split())[:100]
    if not term:
        return []

    def load():
        result = _podcast_index("search/byterm", {"q": term, "max": SEARCH_RESULTS})
        if result is None:
            return None
        shows = []
        for feed in result.get("feeds") or []:
            feed_id = str(feed.get("id") or "")
            if NUMERIC_RE.match(feed_id) and feed.get("title"):
                shows.append(Podcast(id=feed_id, name=feed["title"].strip(),
                                     author=(feed.get("author") or feed.get("ownerName") or "").strip(),
                                     artwork=_artwork(feed)))
        return shows[:SEARCH_RESULTS]

    return _cached(("search", term.lower()), load)


def resolve_show(query: str):
    """What a podcaster typed into the creators form: ("id", podcast id), ("search", term) or
    ("apple", None) for an Apple link Podcast Index doesn't know. Never fetches a URL it's given."""
    text = (query or "").strip()
    if NUMERIC_RE.match(text):
        return "id", text
    match = SONAR_LINK_RE.match(text)
    if match:
        return "id", match.group(1) or match.group(2)
    match = APPLE_PODCASTS_RE.match(text)
    if match:
        found = podcast_id_from_apple(match.group(1))
        return ("id", found) if found else ("apple", None)
    return "search", text


# --- Recaps: a listener's month or year ----------------------------------------------------
#
# Computed from that user's episode_logs (anon-readable). A log's day is its logged_date (the
# day the user picked; "yyyy-MM-dd", or a legacy short date), else its created_at day.

RECAP_FIRST_YEAR = 2024
RECAP_MAX_ROWS = 3000
RECAP_TOP_PODCASTS = 5
PERIOD_RE = re.compile(r"^([0-9]{4})(?:-([0-9]{2}))?\Z")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


@dataclass
class Period:
    key: str        # "2025" or "2025-10"
    start: dt.date  # inclusive
    end: dt.date    # exclusive
    month: Optional[int] = None

    @property
    def label(self) -> str:
        return f"{MONTHS[self.month - 1]} {self.start.year}" if self.month else str(self.start.year)

    @property
    def noun(self) -> str:
        return "month" if self.month else "year"


def parse_period(value: str, today=None) -> Optional[Period]:
    """A recap period ("YYYY" or "YYYY-MM"), or None when it's malformed, before 2024 or in the future."""
    match = PERIOD_RE.match(value or "")
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else None
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if year < RECAP_FIRST_YEAR or (month is not None and not 1 <= month <= 12):
        return None
    if month:
        start = dt.date(year, month, 1)
        end = dt.date(year + (month == 12), month % 12 + 1, 1)
    else:
        start, end = dt.date(year, 1, 1), dt.date(year + 1, 1, 1)
    # Up to a day early, so someone ahead of UTC can share their new month at midnight.
    if start > today + dt.timedelta(days=1):
        return None
    return Period(key=value, start=start, end=end, month=month)


_SHORT_DATE_RE = re.compile(r"^([0-9]{1,2})[/.]([0-9]{1,2})[/.]([0-9]{2,4})\Z")


def log_day(row):
    """The calendar day a log row counts on, or None."""
    for value in (row.get("logged_date"), row.get("created_at")):
        text = (value or "").strip() if isinstance(value, str) else ""
        if not text:
            continue
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            pass
        match = _SHORT_DATE_RE.match(text)
        if match:  # legacy short dates; ambiguous slashes read as US M/d, as the app does
            first, second, year = (int(part) for part in match.groups())
            year += 2000 if year < 100 else 0
            month, day = (first, second) if "/" in text else (second, first)
            try:
                return dt.date(year, month, day)
            except ValueError:
                pass
    return None


def _is_logged(row):
    """Mirrors LOGGED_FILTER: anything but a bare listen-later save."""
    return (not row.get("listen_later") or row.get("is_listened") or (row.get("rating") or 0) > 0
            or row.get("is_loved") or row.get("review") is not None)


@dataclass
class TopPodcast:
    podcast_id: str
    count: int
    podcast: Optional[Podcast] = None

    @property
    def path(self) -> str:
        return f"/sonar/p/{self.podcast_id}"


@dataclass
class Recap:
    username: str
    period: Period
    episodes: int = 0          # distinct episodes logged
    reviews: int = 0
    loved: int = 0
    ratings: int = 0
    average: Optional[float] = None  # 0...5
    days: int = 0               # days with at least one log
    longest_streak: int = 0     # consecutive days with a log
    top_podcasts: list = field(default_factory=list)  # TopPodcasts
    best: Optional[Review] = None  # the highest-rated log
    avatar_url: Optional[str] = None
    badge: Optional[str] = None  # the badge beside their name
    truncated: bool = False

    @property
    def empty(self) -> bool:
        return self.episodes == 0


def summarize_recap(rows, period: Period, username="", top=RECAP_TOP_PODCASTS) -> Recap:
    """The recap numbers for the rows that fall in `period`. Pure, for tests."""
    seen, days, per_podcast = set(), set(), {}
    recap = Recap(username=username, period=period)
    ratings, best, best_key = [], None, None
    for row in rows or []:
        day = log_day(row)
        if day is None or not period.start <= day < period.end or not _is_logged(row):
            continue
        episode_id = str(row.get("episode_id") or "")
        podcast_id = str(row.get("podcast_id") or "")
        days.add(day)
        if episode_id in seen:  # a relisten: counts once
            continue
        seen.add(episode_id)
        if NUMERIC_RE.match(podcast_id):
            first = per_podcast.setdefault(podcast_id, [0, day])
            first[0] += 1
        rating = row.get("rating") if isinstance(row.get("rating"), int) and 0 < row["rating"] <= 10 else None
        if rating:
            ratings.append(rating)
            key = (rating, bool(row.get("is_loved")), bool((row.get("review") or "").strip()), day)
            if best_key is None or key > best_key:
                best_key, best = key, row
        if (row.get("review") or "").strip():
            recap.reviews += 1
        if row.get("is_loved"):
            recap.loved += 1
    recap.episodes = len(seen)
    recap.ratings = len(ratings)
    recap.average = _average(ratings)
    recap.days = len(days)
    streak = longest = 0
    previous = None
    for day in sorted(days):
        streak = streak + 1 if previous is not None and day - previous == dt.timedelta(days=1) else 1
        longest = max(longest, streak)
        previous = day
    recap.longest_streak = longest
    ranked = sorted(per_podcast.items(), key=lambda item: (-item[1][0], item[1][1], item[0]))
    recap.top_podcasts = [TopPodcast(podcast_id=pid, count=count) for pid, (count, _) in ranked[:top]]
    if best is not None:
        recap.best = _review_from_row(best, {})
        recap.best.username = username or None
    return recap


def recap(username: str, period: Period) -> Optional[Recap]:
    """A user's recap for `period`, or None for an unknown user (or a failed lookup)."""
    base = profile(username)
    if base is None or not base.id or not UUID_RE.match(str(base.id)):
        return None

    def load():
        start, end = period.start.isoformat(), period.end.isoformat()
        # Rows whose logged_date or created_at falls in the period; log_day() then decides.
        # (A log backdated into the period is found by logged_date, a legacy-dated one by created_at.)
        rows = _rows(_supabase("episode_logs", {
            "user_id": f"eq.{base.id}",
            "or": f"(and(logged_date.gte.{start},logged_date.lt.{end}),and(created_at.gte.{start},created_at.lt.{end}))",
            "select": REVIEW_COLUMNS + ",logged_date,listen_later,is_listened",
            "order": "created_at.asc",
            "limit": RECAP_MAX_ROWS,
        })) or []
        result = summarize_recap(rows, period, base.username)
        result.truncated = len(rows) >= RECAP_MAX_ROWS
        jobs = [(lambda pid=top.podcast_id: podcast(pid)) for top in result.top_podcasts]
        if result.best is not None:
            jobs.append(lambda: episode(result.best.episode_id or "", result.best.podcast_id or ""))
        jobs.append(lambda: avatar_url(base.id))
        jobs.append(lambda: badges([base.id]).get(base.id))
        resolved = _parallel(jobs)
        for top, show in zip(result.top_podcasts, resolved):
            top.podcast = show
        if result.best is not None:
            result.best.episode = resolved[len(result.top_podcasts)]
        result.avatar_url = resolved[-2]
        result.badge = name_badge(resolved[-1])
        return result

    return _cached(("recap", username.lower(), period.key), load)
