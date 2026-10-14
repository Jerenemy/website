"""Admin review page for the job application bot (getmeajob).

The bot runs `getmeajob serve`, a private API on localhost. These admin-only views call it from the
server with a shared token, so the browser never talks to the bot directly and its screenshots
(which show your phone number and address) are never in /static.
"""
import re
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, url_for

from ..admin.routes import _csrf_token, _validate_csrf, admin_required

bp = Blueprint("jobbot", __name__, url_prefix="/admin/jobs")

ACTIVE = ("queued", "running", "needs_code")
# Where a sent application stands, as the bot works it out from the company's emails (or you set it).
# In the order the tracker lists them: the ones that need you first.
STAGES = {
    "offer": ("Offer", "Offers in hand"),
    "interviewing": ("Moving forward", "Interviews and assessments"),
    "waiting": ("Waiting to hear back", "Applied, no answer yet"),
    "rejected": ("Rejected", "Not moving forward"),
}
# The list page's views, in the sidebar's order: what needs you, where sent applications stand (the
# tracker), then the bot's own queue of dry runs. Each is (name, group).
VIEWS = {
    "codes": ("Codes to enter", "you"),
    "review": ("Ready to review", "you"),
    "attention": ("Needs attention", "you"),
    "sort": ("Emails to sort", "you"),
    "blocked": ("Apply yourself", "you"),
    "offer": ("Offers", "sent"),
    "interviewing": ("Moving forward", "sent"),
    "waiting": ("Waiting to hear back", "sent"),
    "rejected": ("Rejected", "sent"),
    "sent": ("All sent", "sent"),
    "active": ("In progress", "bot"),
    "closed": ("Closed", "bot"),
    "skipped": ("Skipped", "bot"),
    "all": ("Every dry run", "bot"),
}
VIEW_GROUPS = {"you": "Needs you", "sent": "Sent", "bot": "Bot"}
# The first of these with anything in it is where the list opens.
DEFAULT_VIEWS = ("codes", "review", "attention", "sort")


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
    if sub.get("status") in ACTIVE or job.get("editing") or job["status"] == "retry":
        return "active"  # the bot is on it (a `retry` job is tried again on its own)
    # Nothing to fix: the posting no longer takes applications. (`problem` covers bots without `closed`.)
    if job.get("closed") or (sub.get("problem") or {}).get("kind") == "closed":
        return "closed"
    # The site stops the bot for good (captcha, spam flag): the bot never retries it; apply on the site.
    if job.get("blocked") or job["status"] == "blocked":
        return "blocked"
    if job["status"] == "skipped":  # skipped from the review page: out of the queue, in a view of its own
        return "skipped"
    if sub.get("status") in ("failed", "unconfirmed"):
        return "attention"
    if job["status"] == "dry_run_ok":
        return "review"
    if job["status"] == "failed":  # the dry run itself failed: fix it in the chat or rerun
        return "attention"
    return "other"


STATUS_LABELS = {
    "dry_run_ok": "Ready to submit",
    "applied": "Applied",
    "failed": "Failed",
    "skipped": "Skipped",
    "unsupported": "Unsupported site",
    "blocked": "Apply yourself",
    "seen": "Not tried yet",
    "queued": "Queued",
    "running": "Submitting",
    "needs_code": "Needs code",
    "unconfirmed": "Unconfirmed",
    "cancelled": "Cancelled",
    "retry": "Retrying",
}


@bp.app_template_filter("jobbot_status")
def jobbot_status(value):
    return STATUS_LABELS.get(value, str(value or "").replace("_", " "))


EMAIL_KINDS = {
    "code_needed": "Code needed",
    "unconfirmed": "Check submission",
    "not_submitted": "Not submitted",
    "review_ready": "Ready to review",
    "security_code": "Security code",
    "account_verification": "Account verification",
    "account_code": "Account code",
    # emails from the company, filed by the bot's inbox scan
    "confirmation": "Application received",
    "rejection": "Rejection",
    "interview": "Interview",
    "assessment": "Assessment",
    "offer": "Offer",
    "company": "From the company",
}


@bp.app_template_filter("jobbot_email_kind")
def jobbot_email_kind(value):
    return EMAIL_KINDS.get(value, str(value or "email").replace("_", " ").capitalize())


@bp.app_template_filter("jobbot_time")
def jobbot_time(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%b %d, %H:%M UTC")
    except ValueError:
        return value


def _parse(value):
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@bp.app_template_filter("jobbot_ago")
def jobbot_ago(value):
    """How long ago (or, for a time to come, how soon): "just now", "5m ago", "3h ago", "2d ago", else the date."""
    moment = _parse(value) if value else None
    if moment is None:
        return value or ""
    seconds = (datetime.now(timezone.utc) - moment).total_seconds()
    ahead, seconds = seconds < 0, abs(seconds)
    if seconds < 60:
        return "now" if ahead else "just now"
    for size, unit in ((86400 * 7, None), (86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            if unit is None:
                return jobbot_date(value)
            amount = f"{int(seconds // size)}{unit}"
            return f"in {amount}" if ahead else f"{amount} ago"
    return ""


SOURCES = {
    "llm": "AI", "profile": "Profile", "preset": "Preset", "resume": "Resume", "fallback": "Fallback",
    "edit": "Your edit", "rule": "Rule", "prefilled": "Site", "skip": "Left blank", "error": "Error",
}


@bp.app_template_filter("jobbot_source")
def jobbot_source(value):
    """Where an answer came from, as a word: the part before ":" names it (profile:links.linkedin is Profile)."""
    head = str(value or "").split(":", 1)[0].lower()
    return SOURCES.get(head, head.replace("_", " ").capitalize() or "—")


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


def _stage(job):
    """Where a sent application stands. A bot that predates the tracker sends no `stage`: an applied job is
    then waiting to hear back."""
    if "stage" in job:
        return job["stage"]
    if job["category"] != "applied":
        return None
    return {"key": "waiting", "label": STAGES["waiting"][0], "source": "applied", "since": job.get("last_attempt"),
            "email": None, "latest": None, "unsorted": 0}


def _latest(job):
    stage = job["stage"] or {}
    return stage.get("since") or job.get("applied_at") or job.get("last_attempt") or ""


@bp.app_template_filter("jobbot_subject")
def jobbot_subject(value):
    """An email subject without the "[External]" tag the university's mail gateway puts on outside mail."""
    return re.sub(r"^\s*(\[external\]\s*)+", "", str(value or ""), flags=re.I) or "(no subject)"


@bp.app_template_filter("jobbot_date")
def jobbot_date(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%b %d").replace(" 0", " ")
    except ValueError:
        return value


def _reason(job):
    """In a few words, why a job in the bot's queue is where it is: what went wrong, what it waits on."""
    sub = job.get("submission") or {}
    status = sub.get("status")
    problem = sub.get("problem") or job.get("problem") or {}
    if status == "needs_code":
        return "Waiting for the code the company emailed you"
    if status in ("queued", "running"):
        return "Submitting now" if status == "running" else "Queued to submit"
    if job.get("editing"):
        return "Changing the answers"
    if job["status"] == "retry":
        retry = job.get("retry") or {}
        when = jobbot_ago(retry.get("next_at")) if retry.get("next_at") else ""
        again = "tries again on its own" + (f" {when}" if when.startswith("in ") else "")
        return f"{problem['title']} · {again}" if problem.get("title") else again.capitalize()
    if problem.get("title"):
        return problem["title"]
    if status == "unconfirmed":
        return "Submitted, but no confirmation seen"
    missing = job.get("missing_required") or []
    if missing:
        return f"{len(missing)} required question{'' if len(missing) == 1 else 's'} unanswered"
    return ""


def _legacy_view():
    """The list's old addresses (?show=, ?stage=) still open the view they meant."""
    stage = request.args.get("stage")
    if stage:
        return "sent" if stage == "all" else stage
    return request.args.get("show")


@bp.get("/")
@admin_required
def job_list():
    requested = request.args.get("view") or _legacy_view()
    context = dict(views=VIEWS, view_groups=VIEW_GROUPS, stages=STAGES, csrf_token=_csrf_token())
    try:
        data = _api("GET", "/api/jobs?limit=500").json()
    except JobBotError as error:
        return render_template("admin/jobs.html", error=error.message, view=requested or "review", rows=[], counts={},
                               waiting=[], unsorted=[], **context), 503
    jobs = data.get("jobs", [])
    for job in jobs:
        job["category"] = _category(job)
        job["stage"] = _stage(job)
        job["reason"] = _reason(job)
    queue = [job for job in jobs if not job["stage"]]  # a sent application (or one you track) is in the tracker
    tracked = [job for job in jobs if job["stage"]]
    order = list(STAGES)
    tracked.sort(key=_latest, reverse=True)  # newest news first within each stage
    tracked.sort(key=lambda job: order.index(job["stage"]["key"]) if job["stage"]["key"] in order else len(order))
    unsorted = data.get("unsorted") or []
    waiting = [job for job in jobs if (job.get("submission") or {}).get("status") == "needs_code"]
    members = {"codes": waiting, "sort": unsorted, "sent": tracked, "all": queue}
    for key in ("review", "attention", "blocked", "active", "closed", "skipped"):
        members[key] = [job for job in queue if job["category"] == key]
    for key in STAGES:
        members[key] = [job for job in tracked if job["stage"]["key"] == key]
    counts = {key: len(members[key]) for key in VIEWS}
    if requested in VIEWS:
        view = requested
    else:
        view = next((key for key in DEFAULT_VIEWS if counts[key]), "sent" if tracked else "all")
    return render_template("admin/jobs.html", error=None, view=view, rows=members[view], counts=counts,
                           waiting=waiting, unsorted=unsorted, last_pass=data.get("last_pass"), **context)


def _mode(job, sub, editing):
    """Which page a job's page is: what the job needs from you decides what comes first."""
    if sub.get("status") == "needs_code":
        return "code"
    if sub.get("status") in ("queued", "running") or editing:
        return "working"
    if job.get("stage"):
        return "tracked"
    if job["status"] == "retry":
        return "retry"
    category = _category(job)
    return category if category in ("review", "attention", "blocked", "closed") else "other"


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
    job["stage"] = _stage(dict(job, category=_category(job)))
    fields = job.get("fields") or []
    tally = {
        "all": len(fields),
        "ai": sum(1 for f in fields if str(f.get("source") or "").startswith("llm")),
        "issues": sum(1 for f in fields if not f.get("ok", True)),
        "edited": sum(1 for f in fields if (f.get("label"), f.get("education_index")) in edited),
    }
    return render_template("admin/job_detail.html", job=job, sub=sub, active=busy, editing=editing, stages=STAGES,
                           mode=_mode(job, sub, editing), tally=tally, reason=_reason(job),
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
    return redirect(_back(url_for("jobbot.job_detail", job_id=job_id) + anchor))


def _back(default):
    """Where a form on the list or a job's page sends you back to: its `next`, if it is one of these pages."""
    target = request.form.get("next") or ""
    if target.startswith(url_for("jobbot.job_list")) and "//" not in target and "\\" not in target:
        return target
    return default


@bp.post("/emails/assign")
@admin_required
def email_assign():
    back = _back(url_for("jobbot.job_list"))
    if not _validate_csrf(request.form.get("csrf_token")):
        flash("Invalid or missing CSRF token.", "error")
        return redirect(back)
    job_id = request.form.get("job_id") or None
    try:
        _api("POST", "/api/emails/assign", {"message_id": request.form.get("message_id", ""), "job_id": job_id})
        flash("Email filed." if job_id else "Email set aside: it is not about these applications.", "success")
    except JobBotError as error:
        flash(error.message, "error")
    return redirect(back)


@bp.post("/<path:job_id>/stage")
@admin_required
def job_stage(job_id):
    back = _back(url_for("jobbot.job_detail", job_id=job_id) + "#job-status")
    if not _validate_csrf(request.form.get("csrf_token")):
        flash("Invalid or missing CSRF token.", "error")
        return redirect(back)
    value = request.form.get("stage", "")
    try:
        _api("POST", _job_path(job_id, "/stage"), {"stage": value})
        label = STAGES[value][0] if value in STAGES else None
        flash(f"Marked {label}." if label else "Following the company's emails again.", "success")
    except JobBotError as error:
        flash(error.message, "error")
    return redirect(back)


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


@bp.post("/<path:job_id>/rerun")
@admin_required
def job_rerun(job_id):
    return _action(job_id, "rerun", {},
                   "Rerun queued: the bot is filling the form again with its current code.", anchor="#chat")
