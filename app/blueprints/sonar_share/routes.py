from flask import abort, jsonify, make_response, render_template, request, url_for

from . import bp, data, og

TEAM_ID = "9A9HR6WT4K"
BUNDLE_ID = "com.jeremyzay.Sonar"
APP_STORE_ID = "6761410303"
APP_STORE_URL = f"https://apps.apple.com/app/id{APP_STORE_ID}"
SHARE_PATHS = ("/sonar/r/*", "/sonar/e/*", "/sonar/p/*", "/sonar/u/*", "/sonar/l/*")


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


def _render(kind, *, title, description, og_image, deep_link, status=200, **context):
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
        **context,
    )
    response = make_response(html, status)
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


def _dots(rating_points):
    """Five dot fills (0, 0.5 or 1) for a 1...10 rating."""
    if not rating_points:
        return []
    return [max(0.0, min(1.0, (rating_points - level * 2) / 2)) for level in range(5)]


def _stars_text(rating_points):
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
            title="A review on Sonar",
            description="Open it in Sonar, the app for rating and reviewing podcast episodes.",
            og_image=og_image,
            deep_link=deep_link,
        )

    episode = item.episode
    who = f"@{item.username}" if item.username else "Someone"
    episode_title = episode.title if episode else "a podcast episode"
    show = episode.podcast.name if episode and episode.podcast else None
    stars = _stars_text(item.rating)
    headline = f"{who} on {episode_title}"
    summary = item.text or (f"Rated {stars}" if stars else "Logged this episode on Sonar.")
    return _render(
        "review",
        title=headline,
        description=_clip(f"{stars} · {summary}" if stars and item.text else summary, 200),
        og_image=og_image,
        deep_link=deep_link,
        review=item,
        avatar=_avatar(item.username),
        dots=_dots(item.rating),
        show=show,
        episode=episode,
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
            title="A podcast episode on Sonar",
            description="See what listeners think, then rate it yourself on Sonar.",
            og_image=og_image,
            deep_link=deep_link,
        )
    average = data.community_average(episode_id)
    show = item.podcast.name if item.podcast else None
    return _render(
        "episode",
        title=item.title,
        description=(f"{show} · " if show else "") + (f"Rated {average:g}/5 on Sonar" if average else "Rate and review it on Sonar"),
        og_image=og_image,
        deep_link=deep_link,
        episode=item,
        show=show,
        average=average,
        dots=_dots(round(average * 2)) if average else [],
    )


@bp.get("/sonar/p/<podcast_id>")
def shared_podcast(podcast_id):
    item = data.podcast(podcast_id)
    deep_link = f"sonar://podcast/{podcast_id}"
    og_image = _og_url("sonar_share.og_podcast", podcast_id=podcast_id) if data.NUMERIC_RE.match(podcast_id) else _og_brand()
    if item is None:
        return _render(
            "missing",
            title="A podcast on Sonar",
            description="Follow shows and rate their episodes on Sonar.",
            og_image=og_image,
            deep_link=deep_link,
        )
    return _render(
        "podcast",
        title=item.name,
        description=_clip(item.description or (f"By {item.author}" if item.author else "On Sonar"), 200),
        og_image=og_image,
        deep_link=deep_link,
        podcast=item,
    )


@bp.get("/sonar/u/<username>")
def shared_profile(username):
    item = data.profile(username)
    deep_link = f"sonar://user/{username}"
    if item is None:
        if not data.USERNAME_RE.match(username or ""):
            abort(404)
        return _render(
            "missing",
            title=f"@{username} on Sonar",
            description="Follow friends and see what they're listening to on Sonar.",
            og_image=_og_url("sonar_share.og_profile", username=username),
            deep_link=deep_link,
        )
    count = item.logged_count
    return _render(
        "profile",
        title=f"@{item.username} on Sonar",
        description=(f"{count} episodes logged. " if count else "") + "Follow along on Sonar.",
        og_image=_og_url("sonar_share.og_profile", username=item.username),
        deep_link=f"sonar://user/{item.username}",
        profile=item,
        avatar=_avatar(item.username),
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
        title=item.title,
        description=_clip(summary, 200),
        og_image=_og_url("sonar_share.og_list", list_id=list_id),
        deep_link=deep_link,
        sonar_list=item,
        avatar=_avatar(item.username),
        more=max(0, count - len(item.items)),
    )


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
        item = data.profile(username)
        return og.profile_card(item) if item else None

    return _png(("u", username.lower()), build)


@bp.get("/sonar/og/l/<list_id>.png")
def og_list(list_id):
    if not data.UUID_RE.match(list_id):
        abort(404)

    def build():
        item = data.sonar_list(list_id)
        return og.list_card(item) if item else None

    return _png(("l", list_id.lower()), build)


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
