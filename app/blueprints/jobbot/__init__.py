"""Admin review page for the job application bot (getmeajob).

The bot runs `getmeajob serve`, a private API on localhost. These admin-only views call it from the
server with a shared token, so the browser never talks to the bot directly and its screenshots
(which show your phone number and address) are never in /static.
"""
from datetime import datetime
from urllib.parse import quote

import requests
from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, url_for

from ..admin.routes import _csrf_token, _validate_csrf, admin_required

bp = Blueprint("jobbot", __name__, url_prefix="/admin/jobs")

ACTIVE = ("queued", "running", "needs_code")
FILTERS = {
    "review": "Ready to review",
    "active": "In progress",
    "attention": "Needs attention",
    "applied": "Applied",
    "all": "All",
}


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


def _job_path(job_id, suffix=""):
    return f"/api/jobs/{quote(job_id, safe='')}{suffix}"


def _signature(job):
    """Changes whenever the page should reload: job status, submission status, latest edit status."""
    sub = job.get("submission") or {}
    edits = job.get("edits") or []
    last = edits[-1] if edits else {}
    return "|".join([job.get("status") or "", sub.get("status") or "", last.get("id") or "", last.get("status") or ""])


def _category(job):
    sub = job.get("submission") or {}
    if job["status"] == "applied" or sub.get("status") == "applied":
        return "applied"
    if sub.get("status") in ACTIVE or job.get("editing"):
        return "active"
    if sub.get("status") in ("failed", "unconfirmed"):
        return "attention"
    if job["status"] == "dry_run_ok":
        return "review"
    return "other"


STATUS_LABELS = {
    "dry_run_ok": "Ready to submit",
    "applied": "Applied",
    "failed": "Failed",
    "skipped": "Skipped",
    "unsupported": "Unsupported site",
    "seen": "Not tried yet",
    "queued": "Queued",
    "running": "Submitting",
    "needs_code": "Needs code",
    "unconfirmed": "Unconfirmed",
    "cancelled": "Cancelled",
}


@bp.app_template_filter("jobbot_status")
def jobbot_status(value):
    return STATUS_LABELS.get(value, str(value or "").replace("_", " "))


@bp.app_template_filter("jobbot_time")
def jobbot_time(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %H:%M UTC")
    except ValueError:
        return value


@bp.app_template_filter("jobbot_answer")
def jobbot_answer(field):
    value = field.get("answer")
    if value is None or value == "" or value == []:
        return "—"
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    if field.get("kind") == "file":
        value = str(value).replace("\\", "/").rsplit("/", 1)[-1]
    return value


@bp.app_template_filter("jobbot_change_value")
def jobbot_change_value(change, key):
    value = change.get(key)
    if value is None or value == "" or value == []:
        return "(empty)"
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    value = str(value)
    if key == "old" and len(value) > 80:
        value = value[:77] + "..."
    return value


@bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@bp.get("/")
@admin_required
def job_list():
    show = request.args.get("show", "review")
    if show not in FILTERS:
        show = "review"
    try:
        data = _api("GET", "/api/jobs?limit=500").json()
    except JobBotError as error:
        return render_template("admin/jobs.html", error=error.message, jobs=[], counts={}, filters=FILTERS,
                               show=show, waiting=[], csrf_token=_csrf_token()), 503
    jobs = data.get("jobs", [])
    for job in jobs:
        job["category"] = _category(job)
    counts = {key: sum(1 for job in jobs if key == "all" or job["category"] == key) for key in FILTERS}
    waiting = [job for job in jobs if (job.get("submission") or {}).get("status") == "needs_code"]
    shown = [job for job in jobs if show == "all" or job["category"] == show]
    return render_template("admin/jobs.html", error=None, jobs=shown, counts=counts, filters=FILTERS, show=show,
                           waiting=waiting, last_pass=data.get("last_pass"), csrf_token=_csrf_token())


@bp.get("/<path:job_id>")
@admin_required
def job_detail(job_id):
    try:
        job = _api("GET", _job_path(job_id)).json()["job"]
    except JobBotError as error:
        flash(error.message, "error")
        return redirect(url_for("jobbot.job_list"))
    sub = job.get("submission") or {}
    edits = job.get("edits") or []
    editing = bool(job.get("editing"))
    for field in job.get("fields") or []:
        field.setdefault("education_index", None)
    busy = sub.get("status") in ACTIVE or editing
    can_submit = job["status"] == "dry_run_ok" and sub.get("status") not in (*ACTIVE, "applied") and not editing
    can_chat = job["status"] in ("dry_run_ok", "failed") and bool(job.get("fields")) and not busy
    last_done = next((e for e in reversed(edits) if e.get("status") == "done"), None)
    edited = {(c.get("label"), c.get("education_index")) for c in (last_done or {}).get("changes") or []}
    return render_template("admin/job_detail.html", job=job, sub=sub, active=busy, editing=editing,
                           can_submit=can_submit, can_chat=can_chat, edits=edits, edited=edited,
                           signature=_signature(job), needs_force=sub.get("status") == "unconfirmed",
                           csrf_token=_csrf_token())


@bp.get("/<path:job_id>/screenshot")
@admin_required
def job_screenshot(job_id):
    kind = "submission" if request.args.get("kind") == "submission" else "review"
    try:
        response = _api("GET", _job_path(job_id, f"/screenshot?kind={kind}"), timeout=30)
    except JobBotError as error:
        return Response(error.message, status=404 if error.status == 404 else 502, mimetype="text/plain")
    return Response(response.content, mimetype=response.headers.get("Content-Type", "image/png"),
                    headers={"Cache-Control": "no-store"})


@bp.get("/<path:job_id>/status.json")
@admin_required
def job_status(job_id):
    try:
        job = _api("GET", _job_path(job_id)).json()["job"]
    except JobBotError as error:
        return jsonify({"error": error.message}), error.status
    return jsonify({"status": job["status"], "submission": job.get("submission"), "editing": bool(job.get("editing")),
                    "signature": _signature(job)})


def _action(job_id, action, payload, success, anchor=""):
    if not _validate_csrf(request.form.get("csrf_token")):
        flash("Invalid or missing CSRF token.", "error")
    else:
        try:
            _api("POST", _job_path(job_id, f"/{action}"), payload)
            flash(success, "success")
        except JobBotError as error:
            flash(error.message, "error")
    return redirect(url_for("jobbot.job_detail", job_id=job_id) + anchor)


@bp.post("/<path:job_id>/submit")
@admin_required
def job_submit(job_id):
    force = request.form.get("force") == "1"
    return _action(job_id, "submit", {"force": force},
                   "Submission queued. The bot is re-filling the form; this page updates when it finishes.")


@bp.post("/<path:job_id>/code")
@admin_required
def job_code(job_id):
    return _action(job_id, "code", {"code": request.form.get("code", "")}, "Code sent to the bot.")


@bp.post("/<path:job_id>/cancel")
@admin_required
def job_cancel(job_id):
    return _action(job_id, "cancel", {}, "Submission cancelled.")


@bp.post("/<path:job_id>/edit")
@admin_required
def job_edit(job_id):
    return _action(job_id, "edit", {"message": request.form.get("message", "")},
                   "Working on it: the bot is changing the answers and re-filling the form.", anchor="#chat")


@bp.post("/<path:job_id>/skip")
@admin_required
def job_skip(job_id):
    return _action(job_id, "skip", {}, "Marked as skipped.")
