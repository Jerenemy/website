import re
from datetime import datetime, timezone

from flask import abort, jsonify, make_response, redirect, render_template, request, url_for
from markupsafe import Markup

from . import attribution, badge, bp, data, og
from ..admin.routes import _csrf_token, admin_required

TEAM_ID = "9A9HR6WT4K"
BUNDLE_ID = "com.jeremyzay.Sonar"
APP_STORE_ID = "6761410303"
APP_STORE_URL = f"https://apps.apple.com/app/id{APP_STORE_ID}"
SHARE_PATHS = ("/sonar/r/*", "/sonar/e/*", "/sonar/p/*", "/sonar/u/*", "/sonar/l/*", "/sonar/i/*")

# A share path and the app link it stands for. /sonar/go rebuilds the app link from these (never
# from anything the client sends), so it can only ever send people into Sonar or the App Store.
_SHARE_TARGETS = (
    ("review", re.compile(r"^/sonar/r/([0-9a-fA-F-]{36})$"), "sonar://review/{0}"),
    ("episode", re.compile(r"^/sonar/e/([0-9]{1,20})/([0-9]{1,20})$"), "sonar://episode/{0}/{1}"),
    ("podcast", re.compile(r"^/sonar/p/([0-9]{1,20})$"), "sonar://podcast/{0}"),
    ("profile", re.compile(r"^/sonar/u/([A-Za-z0-9_.]{1,30})$"), "sonar://user/{0}"),
    ("list", re.compile(r"^/sonar/l/([0-9a-fA-F-]{36})$"), "sonar://list/{0}"),
    ("invite", re.compile(r"^/sonar/i/([A-Za-z0-9_.]{1,30})$"), "sonar://invite/{0}"),
    ("recap", re.compile(r"^/sonar/u/([A-Za-z0-9_.]{1,30})/recap/([0-9]{4}(?:-[0-9]{2})?)$"), "sonar://recap/{0}/{1}"),
)


def share_target(path):
    """(kind, app link) for a share path like /sonar/r/<id>, or None."""
    for kind, pattern, template in _SHARE_TARGETS:
        match = pattern.fullmatch(path or "")  # fullmatch: "$" alone would let a trailing newline in
        if match:
            return kind, template.format(*match.groups())
    return None


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
                    }
                ]
            }
        }
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


def _render(kind, *, track, title, description, og_image, deep_link, status=200, json_ld=None, noindex=None, **context):
    """Renders a share page. `kind` picks the template branch, `track` is the link's kind for the
    attribution counts (a "missing" page still counts as the review/list/... it was shared as).
    The page URL, canonical link and app-argument never carry ?s=."""
    source = attribution.normalize_source(request.args.get("s"))
    path = request.path
    has_app_link = deep_link is not None and share_target(path) is not None
    html = render_template(
        "works/sonar/share.html",
        kind=kind,
        page_title=title,
        description=description,
        og_image=og_image,
        og_width=og.W,
        og_height=og.H,
        deep_link=deep_link,
        page_url=request.base_url,
        app_store_url=APP_STORE_URL,
        app_store_id=APP_STORE_ID,
        # A malformed id still gets its plain app link (uncounted); /sonar/go only takes valid paths.
        app_href=url_for("sonar_share.go", to="app", k=track, s=source, u=path) if has_app_link else deep_link,
        store_href=url_for("sonar_share.go", to="appstore", k=track, s=source, u=path),
        json_ld=json_ld,
        dots_for=_dots,
        avatar_for=_avatar,
        noindex=kind == "missing" if noindex is None else noindex,
        **context,
    )
    if attribution.should_count(request):
        attribution.record_view(track, source)
    response = make_response(html, status)
    # Not cached by shared caches: the page view is counted when Flask renders it.
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


def _dots(rating_points):
    """Five dot fills (0, 0.5 or 1) for a 1...10 rating."""
    if not rating_points:
        return []
    return [max(0.0, min(1.0, (rating_points - level * 2) / 2)) for level in range(5)]


def _rating_text(rating_points):
    if not rating_points:
        return None
    value = rating_points / 2
    return f"{value:g}/5"


@bp.get("/sonar/r/<log_id>")
def shared_review(log_id):
    item = data.review(log_id)
    deep_link = f"sonar://review/{log_id}"
    og_image = _og_url("sonar_share.og_review", log_id=log_id) if data.UUID_RE.match(log_id) else _og_brand()
    if item is None:
        return _render(
            "missing",
            track="review",
            title="A review on Sonar",
            description="Open it in Sonar, the app for rating and reviewing podcast episodes.",
            og_image=og_image,
            deep_link=deep_link,
        )

    episode = item.episode
    who = f"@{item.username}" if item.username else "Someone"
    episode_title = episode.title if episode else "a podcast episode"
    show = episode.podcast.name if episode and episode.podcast else None
    rating = _rating_text(item.rating)
    headline = f"{who} on {episode_title}"
    summary = item.text or (f"Rated {rating}" if rating else "Logged this episode on Sonar.")
    return _render(
        "review",
        track="review",
        title=headline,
        description=_clip(f"{rating} · {summary}" if rating and item.text else summary, 200),
        og_image=og_image,
        deep_link=deep_link,
        json_ld=_review_ld(item),
        review=item,
        avatar=_avatar(item.username),
        dots=_dots(item.rating),
        show=show,
        episode=episode,
        more=data.more_reviews(item) if item.username else [],
    )


@bp.get("/sonar/e/<podcast_id>/<episode_id>")
def shared_episode(podcast_id, episode_id):
    item = data.episode(episode_id, podcast_id)
    deep_link = f"sonar://episode/{podcast_id}/{episode_id}"
    ids_ok = data.NUMERIC_RE.match(podcast_id) and data.NUMERIC_RE.match(episode_id)
    og_image = (
        _og_url("sonar_share.og_episode", podcast_id=podcast_id, episode_id=episode_id) if ids_ok else _og_brand()
    )
    if item is None:
        return _render(
            "missing",
            track="episode",
            title="A podcast episode on Sonar",
            description="See what listeners think, then rate it yourself on Sonar.",
            og_image=og_image,
            deep_link=deep_link,
        )
    average, rating_count = data.community_rating(episode_id)
    reviews = data.episode_reviews(episode_id)
    for review in reviews:
        review.episode = item
    show = item.podcast.name if item.podcast else None
    rated = f"Rated {average:g}/5 by {rating_count} {'listener' if rating_count == 1 else 'listeners'} on Sonar" if average else None
    return _render(
        "episode",
        track="episode",
        title=item.title,
        description=_clip((f"{show} · " if show else "") + (rated or "Rate and review it on Sonar")
                          + (f". “{reviews[0].text}”" if reviews else ""), 200),
        og_image=og_image,
        deep_link=deep_link,
        json_ld=_episode_ld(item, average, rating_count, reviews),
        episode=item,
        show=show,
        average=average,
        rating_count=rating_count,
        dots=_dots(round(average * 2)) if average else [],
        reviews=reviews,
    )


@bp.get("/sonar/p/<podcast_id>")
def shared_podcast(podcast_id):
    item = data.podcast(podcast_id)
    deep_link = f"sonar://podcast/{podcast_id}"
    og_image = _og_url("sonar_share.og_podcast", podcast_id=podcast_id) if data.NUMERIC_RE.match(podcast_id) else _og_brand()
    if item is None:
        return _render(
            "missing",
            track="podcast",
            title="A podcast on Sonar",
            description="Follow shows and rate their episodes on Sonar.",
            og_image=og_image,
            deep_link=deep_link,
        )
    return _render(
        "podcast",
        track="podcast",
        title=item.name,
        description=_clip(item.description or (f"By {item.author}" if item.author else "On Sonar"), 200),
        og_image=og_image,
        deep_link=deep_link,
        json_ld=_ld({"@type": "PodcastSeries", "name": item.name, "url": request.base_url,
                     "author": {"@type": "Person", "name": item.author} if item.author else None,
                     "image": item.artwork, "description": _clip(item.description, 300) or None}),
        podcast=item,
    )


@bp.get("/sonar/u/<username>")
def shared_profile(username):
    page = data.profile_page(username)
    deep_link = f"sonar://user/{username}"
    if page is None:
        if not data.USERNAME_RE.match(username or ""):
            abort(404)
        return _render(
            "missing",
            track="profile",
            title=f"@{username} on Sonar",
            description="Follow friends and see what they're listening to on Sonar.",
            og_image=_og_url("sonar_share.og_profile", username=username),
            deep_link=deep_link,
        )
    item = page.profile
    return _render(
        "profile",
        track="profile",
        title=f"@{item.username} on Sonar",
        description=_profile_description(page),
        og_image=_og_url("sonar_share.og_profile", username=item.username),
        deep_link=f"sonar://user/{item.username}",
        json_ld=_profile_ld(page),
        profile=item,
        page=page,
        avatar=_avatar(item.username),
    )


@bp.get("/sonar/i/<username>")
def invite(username):
    """An invite from a Sonar user. An unknown or malformed name still gets a friendly invite."""
    valid = bool(data.USERNAME_RE.match(username or ""))
    page = data.profile_page(username) if valid else None
    if page is None:
        return _render(
            "invite",
            track="invite",
            title="You're invited to Sonar",
            description="Rate, review and remember the podcast episodes you love, and see what your friends are listening to.",
            og_image=_og_url("sonar_share.og_invite", username=username) if valid else _og_brand(),
            deep_link=f"sonar://invite/{username}" if valid else None,
            page=None,
            inviter=None,
        )
    name = page.profile.username
    return _render(
        "invite",
        track="invite",
        title=f"@{name} invited you to Sonar",
        description=_clip(f"Join @{name} on Sonar: rate, review and remember the podcast episodes you love. "
                          + _profile_stats_text(page), 200),
        og_image=_og_url("sonar_share.og_invite", username=name),
        deep_link=f"sonar://invite/{name}",
        json_ld=_profile_ld(page, url=url_for("sonar_share.shared_profile", username=name, _external=True)),
        page=page,
        inviter=name,
        avatar=_avatar(name),
    )


@bp.get("/sonar/l/<list_id>")
def shared_list(list_id):
    item = data.sonar_list(list_id)
    deep_link = f"sonar://list/{list_id}"
    if item is None:
        # Private, deleted, or not readable with the public key: a friendly 404 that still
        # offers the app (where the owner, or anyone the list is shared with, can open it).
        return _render(
            "missing",
            track="list",
            title="A list on Sonar",
            description="This list isn't available on the web. It may be private or deleted; try opening it in Sonar.",
            og_image=_og_brand(),
            deep_link=deep_link,
            status=404,
        )
    who = f"@{item.username}" if item.username else "someone"
    count = item.item_count
    summary = item.description or (f"{count} {'entry' if count == 1 else 'entries'}, curated by {who}." if count else f"A list by {who}.")
    return _render(
        "list",
        track="list",
        title=item.title,
        description=_clip(summary, 200),
        og_image=_og_url("sonar_share.og_list", list_id=list_id),
        deep_link=deep_link,
        json_ld=_ld({
            "@type": "ItemList", "name": item.title, "url": request.base_url,
            "description": item.description, "numberOfItems": count or None,
            "itemListElement": [
                {"@type": "ListItem", "position": index + 1, "name": entry.title,
                 "url": request.host_url.rstrip("/") + entry.path}
                for index, entry in enumerate(item.items) if entry.title
            ] or None,
        }),
        sonar_list=item,
        avatar=_avatar(item.username),
        more=max(0, count - len(item.items)),
    )


# --- Recaps ------------------------------------------------------------------------------

@bp.get("/sonar/u/<username>/recap/<period>")
def shared_recap(username, period):
    """A listener's month (YYYY-MM) or year (YYYY). A malformed, pre-2024 or future period is a 404."""
    parsed = data.parse_period(period)
    if parsed is None or not data.USERNAME_RE.match(username or ""):
        abort(404)
    item = data.recap(username, parsed)
    og_image = _og_url("sonar_share.og_recap", username=username, period=period)
    if item is None:
        return _render(
            "missing",
            track="recap",
            title=f"@{username}'s {parsed.label} on Sonar",
            description="Open it in Sonar, the app for rating and reviewing podcast episodes.",
            og_image=og_image,
            deep_link=f"sonar://recap/{username}/{period}",
            status=404,
        )
    name = item.username
    return _render(
        "recap",
        track="recap",
        title=f"@{name}'s {parsed.label} on Sonar",
        description=_recap_description(item),
        og_image=og_image,
        deep_link=f"sonar://recap/{name}/{period}",
        noindex=item.empty,
        recap=item,
        avatar=_avatar(name),
        dots=_dots(item.best.rating) if item.best else [],
        average_dots=_dots(round(item.average * 2)) if item.average else [],
    )


def _recap_description(item):
    when = item.period.label
    if item.empty:
        return f"@{item.username} hasn't logged anything in {when} yet. Rate, review and remember the episodes you love on Sonar."
    noun = "episode" if item.episodes == 1 else "episodes"
    text = f"@{item.username}'s {when} on Sonar: {item.episodes:,} {noun} logged"
    extras = []
    if item.reviews:
        extras.append(f"{item.reviews:,} {'review' if item.reviews == 1 else 'reviews'}")
    if item.loved:
        extras.append(f"{item.loved:,} loved")
    text += (", " + ", ".join(extras) if extras else "") + "."
    top = next((t.podcast.name for t in item.top_podcasts if t.podcast), None)
    if top:
        text += f" Top show: {top}."
    return _clip(text, 200)


# --- Creators ------------------------------------------------------------------------------

def _creator_page(status=200, **context):
    source = attribution.normalize_source(request.args.get("s"))
    html = render_template(
        "works/sonar/creators.html",
        page_url=request.base_url,
        app_store_url=APP_STORE_URL,
        app_store_id=APP_STORE_ID,
        og_width=og.W,
        og_height=og.H,
        source=source,
        dots_for=_dots,
        avatar_for=_avatar,
        **context,
    )
    if status == 200 and attribution.should_count(request):
        attribution.record_view("creator", source)
    response = make_response(html, status)
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@bp.get("/sonar/creators")
def creators():
    """For podcasters: what Sonar is, and a box to find their show's badge.

    ?q= takes a Podcast Index id, a Sonar link, an Apple Podcasts link (resolved through Podcast
    Index; the link itself is never fetched) or a show's name."""
    query = (request.args.get("q") or "").strip()[:300]
    results, message = None, None
    if query:
        how, value = data.resolve_show(query)
        if how == "id":
            return redirect(url_for("sonar_share.creator", podcast_id=value), code=303)
        if how == "apple":
            message = "We couldn't match that Apple Podcasts link to a show. Try the show's name instead."
        else:
            results = data.search_podcasts(value)
            if results is None:
                message = "Search isn't available right now. Paste your show's Podcast Index id or its Sonar link instead."
            elif not results:
                message = f"No shows found for “{_clip(value, 60)}”."
    return _creator_page(
        kind="landing",
        page_title="Sonar for podcasters",
        description="Show listeners what they think of your podcast: a live “Rated on Sonar” badge for your site and show notes.",
        og_image=_og_brand(),
        query=query,
        results=results,
        message=message,
        # Our own SVG, every piece of text escaped by badge.svg: safe to inline.
        example_dark=Markup(badge.svg(*badge.rating_text(4.6, 128), theme="dark")),
        example_light=Markup(badge.svg(*badge.rating_text(4.6, 128), theme="light")),
        example_empty=Markup(badge.svg(*badge.rating_text(None, 0), theme="dark")),
    )


@bp.get("/sonar/creators/p/<podcast_id>")
def creator(podcast_id):
    show = data.podcast(podcast_id) if data.NUMERIC_RE.match(podcast_id) else None
    if show is None:
        return _creator_page(
            kind="unknown",
            status=404,
            page_title="Show not found",
            description="We couldn't find that show on Podcast Index.",
            og_image=_og_brand(),
            query=podcast_id if data.NUMERIC_RE.match(podcast_id) else "",
            results=None,
            message=None,
        )
    stats = data.creator_stats(podcast_id)
    rating = data.podcast_rating(podcast_id) or (None, 0)
    average, count = rating
    show_link = url_for("sonar_share.shared_podcast", podcast_id=podcast_id, s="creator", _external=True)
    badge_url = url_for("sonar_share.badge_podcast", podcast_id=podcast_id, _external=True)
    snippets = _snippets(show_link, badge_url, f"{show.name} on Sonar")
    episodes = []
    for stat in (stats.top_episodes if stats else []):
        link = url_for("sonar_share.shared_episode", podcast_id=podcast_id, episode_id=stat.episode_id, s="creator",
                       _external=True)
        image = url_for("sonar_share.badge_episode", podcast_id=podcast_id, episode_id=stat.episode_id, _external=True)
        title = stat.episode.title if stat.episode else "An episode"
        episodes.append({"stat": stat, "path": f"/sonar/e/{podcast_id}/{stat.episode_id}",
                         "snippets": _snippets(link, image, f"{title} on Sonar"),
                         "badge": url_for("sonar_share.badge_episode", podcast_id=podcast_id, episode_id=stat.episode_id)})
    rated = f"Rated {average:.1f}/5 from {count:,} {'rating' if count == 1 else 'ratings'} on Sonar" if average else "Rate it on Sonar"
    return _creator_page(
        kind="show",
        page_title=f"{show.name} on Sonar",
        description=_clip(f"{show.name}: {rated}. Embed the live rating badge on your site and in your show notes.", 200),
        og_image=_og_url("sonar_share.og_creator", podcast_id=podcast_id),
        podcast=show,
        stats=stats,
        average=average,
        count=count,
        average_dots=_dots(round(average * 2)) if average else [],
        snippets=snippets,
        episodes=episodes,
        badge_path=url_for("sonar_share.badge_podcast", podcast_id=podcast_id),
        app_href=url_for("sonar_share.go", to="app", k="creator", s="creator", u=f"/sonar/p/{podcast_id}"),
        show_href=f"/sonar/p/{podcast_id}?s=creator",
    )


def _snippets(link, image, alt):
    """Embed code for a badge, per theme: HTML, Markdown and the plain link."""
    out = {}
    for theme in badge.THEMES:
        src = image + ("?theme=light" if theme == "light" else "")
        html = (f'<a href="{_attr(link)}"><img src="{_attr(src)}" alt="{_attr(alt)}" '
                f'width="{badge.WIDTH}" height="{badge.HEIGHT}"></a>')
        markdown_alt = alt.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        out[theme] = {"html": html, "markdown": f"[![{markdown_alt}]({src})]({link})", "link": link}
    return out


def _attr(value):
    return (value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;"))


# --- Attribution ---------------------------------------------------------------------------

@bp.get("/sonar/go")
def go():
    """Counts a tap on "Open in Sonar" or "Get Sonar", then sends it on.

    ?to=app|appstore &k=<kind> &s=<source> &u=<share path>. Never an open redirect: the App Store
    URL is fixed, and the app link is rebuilt here from a share path that must match one of
    _SHARE_TARGETS exactly.
    """
    target = request.args.get("to", "")
    if target not in attribution.TARGETS:
        abort(400)
    parsed = share_target(request.args.get("u", ""))
    if target == "app":
        if parsed is None:
            abort(400)
        destination = parsed[1]
    else:
        destination = APP_STORE_URL
    requested = attribution.normalize_kind(request.args.get("k"))
    if requested in attribution.PAGE_KINDS:
        kind = requested
    else:
        kind = parsed[0] if parsed else requested
    if attribution.should_count(request):
        attribution.record_click(kind, request.args.get("s"), target)
    response = redirect(destination, code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@bp.get("/admin/sonar")
@admin_required
def share_stats():
    response = make_response(render_template(
        "admin/sonar_stats.html",
        periods=[attribution.summary(7), attribution.summary(30)],
        sources=attribution.SOURCES,
        csrf_token=_csrf_token(),
    ))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


# --- Structured data and descriptions ------------------------------------------------------

def _ld(node):
    """A schema.org JSON-LD object without empty values."""
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if v not in (None, "", [], {})}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return strip({"@context": "https://schema.org", **node})


def _person(username):
    if not username:
        return None
    return {"@type": "Person", "name": f"@{username}", "alternateName": username,
            "url": url_for("sonar_share.shared_profile", username=username, _external=True)}


def _episode_node(episode):
    if episode is None:
        return {"@type": "PodcastEpisode", "name": "A podcast episode"}
    return {
        "@type": "PodcastEpisode",
        "name": episode.title,
        "image": episode.artwork,
        "url": url_for("sonar_share.shared_episode", podcast_id=episode.podcast.id, episode_id=episode.id, _external=True)
        if episode.podcast and data.NUMERIC_RE.match(episode.podcast.id or "") else None,
        "partOfSeries": {"@type": "PodcastSeries", "name": episode.podcast.name} if episode.podcast else None,
    }


def _rating_node(rating_points):
    if not rating_points:
        return None
    return {"@type": "Rating", "ratingValue": rating_points / 2, "bestRating": 5, "worstRating": 0.5}


def _review_ld(item):
    return _ld({
        "@type": "Review",
        "url": request.base_url,
        "reviewBody": item.text,
        "reviewRating": _rating_node(item.rating),
        "author": _person(item.username),
        "datePublished": (item.created_at or "")[:10] or None,
        "itemReviewed": _episode_node(item.episode),
        "publisher": {"@type": "Organization", "name": "Sonar"},
    })


def _episode_ld(episode, average, rating_count, reviews):
    node = _episode_node(episode)
    node["url"] = request.base_url
    if average and rating_count:
        node["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": average, "ratingCount": rating_count,
                                   "bestRating": 5, "worstRating": 0.5}
    node["review"] = [
        {"@type": "Review", "reviewBody": review.text, "author": _person(review.username),
         "reviewRating": _rating_node(review.rating),
         "url": url_for("sonar_share.shared_review", log_id=review.id, _external=True)}
        for review in reviews
    ] or None
    return _ld(node)


def _profile_ld(page, url=None):
    item = page.profile
    stats = []
    if page.followers is not None:
        stats.append({"@type": "InteractionCounter", "interactionType": "https://schema.org/FollowAction",
                      "userInteractionCount": page.followers})
    person = _person(item.username)
    person["image"] = page.avatar_url
    person["interactionStatistic"] = stats or None
    return _ld({"@type": "ProfilePage", "url": url or request.base_url, "mainEntity": person})


def _profile_stats_text(page):
    parts = []
    count = page.profile.logged_count
    if count:
        parts.append(f"{count:,} {'episode' if count == 1 else 'episodes'} logged")
    if page.followers:
        parts.append(f"{page.followers:,} {'follower' if page.followers == 1 else 'followers'}")
    return (" · ".join(parts) + ".") if parts else ""


def _profile_description(page):
    name = page.profile.username
    text = f"@{name} rates and reviews podcast episodes on Sonar."
    stats = _profile_stats_text(page)
    if stats:
        text += " " + stats
    latest = next((r for r in page.recent_reviews or [] if r.episode), None)
    if latest:
        show = latest.episode.podcast.name if latest.episode.podcast else None
        text += f" Latest: {latest.episode.title}" + (f" ({show})." if show else ".")
    return _clip(text, 200)


# --- Open Graph images ---------------------------------------------------------------------

def _og_url(endpoint, **values):
    return url_for(endpoint, _external=True, **values)


def _og_brand():
    return url_for("sonar_share.og_brand", _external=True)


def _png(key, build):
    png, cache_control = og.render(key, build)
    response = make_response(png)
    response.mimetype = "image/png"
    response.headers["Cache-Control"] = cache_control
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Robots-Tag"] = "noindex"
    response.add_etag()
    return response.make_conditional(request)


@bp.get("/sonar/og/brand.png")
def og_brand():
    return _png(("brand",), og.brand_card)


@bp.get("/sonar/og/r/<log_id>.png")
def og_review(log_id):
    if not data.UUID_RE.match(log_id):
        abort(404)

    def build():
        item = data.review(log_id)
        return og.review_card(item) if item else None

    return _png(("r", log_id.lower()), build)


@bp.get("/sonar/og/e/<podcast_id>/<episode_id>.png")
def og_episode(podcast_id, episode_id):
    if not (data.NUMERIC_RE.match(podcast_id) and data.NUMERIC_RE.match(episode_id)):
        abort(404)

    def build():
        item = data.episode(episode_id, podcast_id)
        return og.episode_card(item, data.community_average(episode_id)) if item else None

    return _png(("e", podcast_id, episode_id), build)


@bp.get("/sonar/og/p/<podcast_id>.png")
def og_podcast(podcast_id):
    if not data.NUMERIC_RE.match(podcast_id):
        abort(404)

    def build():
        item = data.podcast(podcast_id)
        return og.podcast_card(item) if item else None

    return _png(("p", podcast_id), build)


@bp.get("/sonar/og/u/<username>.png")
def og_profile(username):
    if not data.USERNAME_RE.match(username):
        abort(404)

    def build():
        page = data.profile_page(username)
        return og.profile_card(page.profile, page.avatar_url) if page else None

    return _png(("u", username.lower()), build)


@bp.get("/sonar/og/i/<username>.png")
def og_invite(username):
    if not data.USERNAME_RE.match(username):
        abort(404)

    def build():
        page = data.profile_page(username)
        if page is None:
            og.mark_degraded()  # a generic invite: the name may exist soon, so don't keep it long
        return og.invite_card(page)

    return _png(("i", username.lower()), build)


@bp.get("/sonar/og/l/<list_id>.png")
def og_list(list_id):
    if not data.UUID_RE.match(list_id):
        abort(404)

    def build():
        item = data.sonar_list(list_id)
        return og.list_card(item) if item else None

    return _png(("l", list_id.lower()), build)


@bp.get("/sonar/og/u/<username>/recap/<period>.png")
def og_recap(username, period):
    parsed = data.parse_period(period)
    if parsed is None or not data.USERNAME_RE.match(username):
        abort(404)

    def build():
        item = data.recap(username, parsed)
        if item is not None and parsed.end > _utc_today():
            og.mark_degraded()  # a period still running: its numbers change, keep it briefly
        return og.recap_card(item) if item else None

    return _png(("recap", username.lower(), period), build)


@bp.get("/sonar/og/creator/p/<podcast_id>.png")
def og_creator(podcast_id):
    if not data.NUMERIC_RE.match(podcast_id):
        abort(404)

    def build():
        show = data.podcast(podcast_id)
        if show is None:
            return None
        rating = data.podcast_rating(podcast_id)
        if rating is None:
            og.mark_degraded()
        average, count = rating or (None, 0)
        return og.creator_card(show, average, count)

    return _png(("creator", podcast_id), build)


def _utc_today():
    return datetime.now(timezone.utc).date()


# --- Badges --------------------------------------------------------------------------------

BADGE_CACHE = "public, max-age=3600"
BADGE_CACHE_SHORT = "public, max-age=300"


def _badge(rating):
    """An SVG badge response. `rating` is (average, count), or None when the lookup failed.
    Fetches of the badge aren't page views; only taps through it are (?s=creator)."""
    average, count = rating or (None, 0)
    value, description = badge.rating_text(average, count)
    response = make_response(badge.svg(value, description, request.args.get("theme")))
    response.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
    response.headers["Cache-Control"] = BADGE_CACHE if rating is not None else BADGE_CACHE_SHORT
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Robots-Tag"] = "noindex"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.add_etag()
    return response.make_conditional(request)


@bp.get("/sonar/badge/p/<podcast_id>.svg")
def badge_podcast(podcast_id):
    if not data.NUMERIC_RE.match(podcast_id):
        abort(404)
    return _badge(data.podcast_rating(podcast_id))


@bp.get("/sonar/badge/e/<podcast_id>/<episode_id>.svg")
def badge_episode(podcast_id, episode_id):
    if not (data.NUMERIC_RE.match(podcast_id) and data.NUMERIC_RE.match(episode_id)):
        abort(404)
    return _badge(data.episode_rating(episode_id))


def _avatar(username):
    top, bottom = og.avatar_colors(username or "?")
    return {
        "initial": og.avatar_initial(username),
        "top": "#%02x%02x%02x" % top,
        "bottom": "#%02x%02x%02x" % bottom,
    }


def _clip(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
