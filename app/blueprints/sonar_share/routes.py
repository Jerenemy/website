from flask import abort, jsonify, make_response, render_template, request

from . import bp, data

TEAM_ID = "9A9HR6WT4K"
BUNDLE_ID = "com.jeremyzay.Sonar"
APP_STORE_ID = "6761410303"
APP_STORE_URL = f"https://apps.apple.com/app/id{APP_STORE_ID}"
SHARE_PATHS = ("/sonar/r/*", "/sonar/e/*", "/sonar/p/*", "/sonar/u/*")


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


def _render(kind, *, title, description, image=None, deep_link, status=200, **context):
    html = render_template(
        "works/sonar/share.html",
        kind=kind,
        page_title=title,
        description=description,
        image=image,
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
    if item is None:
        return _render(
            "missing",
            title="A review on Sonar",
            description="Open it in Sonar, the app for rating and reviewing podcast episodes.",
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
        image=episode.artwork if episode else None,
        deep_link=deep_link,
        review=item,
        dots=_dots(item.rating),
        show=show,
        episode=episode,
    )


@bp.get("/sonar/e/<podcast_id>/<episode_id>")
def shared_episode(podcast_id, episode_id):
    item = data.episode(episode_id, podcast_id)
    deep_link = f"sonar://episode/{podcast_id}/{episode_id}"
    if item is None:
        return _render(
            "missing",
            title="A podcast episode on Sonar",
            description="See what listeners think, then rate it yourself on Sonar.",
            deep_link=deep_link,
        )
    average = data.community_average(episode_id)
    show = item.podcast.name if item.podcast else None
    return _render(
        "episode",
        title=item.title,
        description=(f"{show} · " if show else "") + (f"Rated {average:g}/5 on Sonar" if average else "Rate and review it on Sonar"),
        image=item.artwork,
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
    if item is None:
        return _render(
            "missing",
            title="A podcast on Sonar",
            description="Follow shows and rate their episodes on Sonar.",
            deep_link=deep_link,
        )
    return _render(
        "podcast",
        title=item.name,
        description=_clip(item.description or (f"By {item.author}" if item.author else "On Sonar"), 200),
        image=item.artwork,
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
            deep_link=deep_link,
        )
    count = item.logged_count
    return _render(
        "profile",
        title=f"@{item.username} on Sonar",
        description=(f"{count} episodes logged. " if count else "") + "Follow along on Sonar.",
        deep_link=f"sonar://user/{item.username}",
        profile=item,
    )


def _clip(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
