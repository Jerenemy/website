"""What is left here of the job application bot's pages, which moved to Sisyphus (sisyphus.fail, its own app
and repo).

Old addresses, including the links in emails already sent, go to the same page there. Texts from companies still
arrive here: the phone shortcut posts to this address, and it needs no login of Sisyphus's.
"""
import hmac
from urllib.parse import quote

import requests
from flask import Blueprint, current_app, jsonify, redirect, request

bp = Blueprint("jobbot", __name__, url_prefix="/admin/jobs")
short = Blueprint("sisyphus", __name__)
SISYPHUS = "https://sisyphus.fail"


class JobBotError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _api(method, path, payload=None, timeout=15):
    base = (current_app.config.get("JOBBOT_API_URL") or "").rstrip("/")
    token = current_app.config.get("JOBBOT_API_TOKEN")
    if not base or not token:
        raise JobBotError(503, "The job bot is not configured: set JOBBOT_API_URL and JOBBOT_API_TOKEN.")
    try:
        response = requests.request(
            method,
            base + path,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(3, timeout),
        )
    except requests.RequestException as error:
        current_app.logger.warning("job bot API request failed: %s %s (%s)", method, path, error)
        raise JobBotError(503, "The job bot is not reachable. Is `getmeajob serve` running?") from None
    if response.status_code >= 400:
        try:
            message = response.json().get("error") or response.reason
        except ValueError:
            message = response.reason
        raise JobBotError(response.status_code, message)
    return response


@bp.get("/")
def job_list():
    view = request.args.get("view")
    return redirect(f"{SISYPHUS}/jobs" + (f"?view={quote(view, safe='')}" if view else ""))


@bp.get("/<path:job_id>")
def job_detail(job_id):
    return redirect(f"{SISYPHUS}/jobs/{quote(job_id, safe='')}")


@bp.post("/texts")
def text_message():
    """A text a company sent you (an assessment link, an interview invite), forwarded by a phone shortcut and
    filed by the bot under the application it is about, like an email (README: "Texts from companies").
    No admin login: the shortcut sends `Authorization: Bearer <JOBBOT_TEXT_TOKEN>`, which only files texts."""
    expected = current_app.config.get("JOBBOT_TEXT_TOKEN") or ""
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    payload = {"from": str(data.get("from") or ""), "body": str(data.get("body") or ""), "at": data.get("at") or None}
    try:
        result = _api("POST", "/api/texts", payload).json()
    except JobBotError as error:
        return jsonify(error=error.message), error.status
    filed = result.get("filed") or []
    if not filed:
        summary = "Not about any application you sent."
    elif any(f.get("match") == "guess" for f in filed):
        summary = f"Could be about {len(filed)} applications at {filed[0].get('company')}: sort it on the jobs page."
    else:
        summary = "; ".join(f"{f.get('company')}: {f.get('title')} ({f.get('kind')})" for f in filed)
    return jsonify(dict(result, summary=summary))


@short.get("/sisyphus", defaults={"rest": ""})
@short.get("/sisyphus/<path:rest>")
@short.get("/proxy", defaults={"rest": ""})
@short.get("/proxy/<path:rest>")
def sisyphus(rest):
    """jeremyzay.com/sisyphus, wherever it is typed or linked."""
    return redirect(f"{SISYPHUS}/{quote(rest)}", code=301)
