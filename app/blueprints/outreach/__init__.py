"""Private dashboards for my CEO outreach routine, under /admin/outreach.

The routine runs on my Mac (the private ceo-outreach repo). After each run its tools/sync_dashboard.py
POSTs leads.csv, bounces.csv and its A/B scoreboard to /admin/outreach/sync with OUTREACH_SYNC_TOKEN,
and gets back the reply examples, which the Voice tab edits here. So the server holds a copy of
the leads (read only here) and the one live copy of the examples. Everything lives in
OUTREACH_DATA_DIR (instance/outreach by default), untracked, so nothing about the leads is in git.
"""
import csv
import io
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for

from ..admin.routes import _csrf_token, _validate_csrf, admin_required

bp = Blueprint("outreach", __name__)

REPLIED = {"replied", "reply-drafted", "follow-up-later", "meeting-requested", "call-booked", "not-interested"}
MEETING = {"meeting-requested", "call-booked"}
NOT_SENT = {"drafted", "skipped", "no-email", "bounced"}
FILTERS = [("all", "All"), ("replied", "Replied"), ("waiting", "Waiting"), ("cold", "Cold or bounced")]
EXAMPLE_FIELDS = ("title", "context", "ceo_message", "reply", "why")
FIELD_MAX = {"title": 120, "context": 400, "ceo_message": 4000, "reply": 4000, "why": 1000}
GMAIL_THREAD = "https://mail.google.com/mail/u/jzay@wesleyan.edu/#all/{}"


# ---- storage ---------------------------------------------------------------------------------

def _dir() -> Path:
    path = Path(current_app.config["OUTREACH_DATA_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(name: str, text: str) -> None:
    """Atomic: a half-written file is never read."""
    folder = _dir()
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{name}.")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    os.replace(tmp, folder / name)


def _read(name: str) -> str | None:
    path = _dir() / name
    return path.read_text(encoding="utf-8") if path.exists() else None


def load_leads() -> list[dict]:
    text = _read("leads.csv")
    return list(csv.DictReader(io.StringIO(text))) if text else []


def load_stats() -> dict | None:
    text = _read("stats.json")
    return json.loads(text) if text else None


def load_examples() -> list[dict]:
    text = _read("reply_examples.json")
    return json.loads(text) if text else []


def save_examples(examples: list[dict]) -> None:
    _write("reply_examples.json", json.dumps(examples, indent=2, ensure_ascii=False))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_example(raw: dict, source: str) -> dict:
    example = {k: str(raw.get(k) or "").strip()[: FIELD_MAX[k]] for k in EXAMPLE_FIELDS}
    example["id"] = str(raw.get("id") or uuid4().hex)[:64]
    example["source"] = raw.get("source") if raw.get("source") in ("hypothetical", "real") else source
    example["updated_at"] = str(raw.get("updated_at") or _now())
    return example


# ---- what the pages show ---------------------------------------------------------------------

def _went_out(lead: dict) -> bool:
    return lead.get("status") not in NOT_SENT


def summary(leads: list[dict]) -> dict:
    out = [l for l in leads if _went_out(l)]
    replies = [l for l in out if l.get("status") in REPLIED]
    return {
        "sent": len(out),
        "replies": len(replies),
        "rate": len(replies) / len(out) if out else None,
        "positive": sum(l["status"] != "not-interested" for l in replies),
        "meetings": sum(l.get("status") in MEETING for l in out),
        "bounced": sum(l.get("status") in {"bounced", "no-email"} for l in leads),
    }


def _matches(lead: dict, show: str) -> bool:
    status = lead.get("status", "")
    if show == "replied":
        return status in REPLIED
    if show == "waiting":
        return status in {"sent", "drafted", "nudge-drafted"}
    if show == "cold":
        return status in {"cold", "bounced", "no-email", "skipped"}
    return True


def email_rows(leads: list[dict], show: str) -> list[dict]:
    rows = []
    for lead in leads:
        if not _matches(lead, show):
            continue
        nudges = [n for n in (lead.get("nudges") or "").split("|") if n]
        rows.append({
            "name": lead.get("name", ""),
            "company": lead.get("company", ""),
            "company_url": lead.get("company_url", ""),
            "hook": lead.get("hook", ""),
            "variant": lead.get("variant", ""),
            "greeting": lead.get("greeting", ""),
            "nudges": nudges,
            "status": lead.get("status", ""),
            "replied": lead.get("status") in REPLIED,
            "replied_after": lead.get("replied_after", ""),
            "first_contacted": lead.get("first_contacted", ""),
            "last_activity": lead.get("last_activity", ""),
            "follow_up_on": lead.get("follow_up_on", ""),
            "thread_url": GMAIL_THREAD.format(lead["thread_id"]) if lead.get("thread_id") else None,
        })
    # replies on top, then newest first
    rows.sort(key=lambda r: r["first_contacted"], reverse=True)
    rows.sort(key=lambda r: not r["replied"])
    return rows


def _page(template: str, **context):
    response = current_app.make_response(render_template(
        template, csrf_token=_csrf_token(), synced_at=_read("synced_at"), **context))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


# ---- pages -----------------------------------------------------------------------------------

@bp.get("/admin/outreach")
@admin_required
def emails():
    show = request.args.get("show", "all")
    if show not in dict(FILTERS):
        show = "all"
    leads = load_leads()
    return _page("admin/outreach_emails.html", tab="emails", summary=summary(leads),
                 rows=email_rows(leads, show), has_data=bool(leads),
                 filter_tabs=[(url_for("outreach.emails", **({"show": key} if key != "all" else {})), text, key == show)
                              for key, text in FILTERS])


@bp.get("/admin/outreach/ab")
@admin_required
def ab_test():
    return _page("admin/outreach_ab.html", tab="ab", stats=load_stats())


@bp.get("/admin/outreach/voice")
@admin_required
def voice():
    examples = load_examples()
    open_ = [e for e in examples if not e["reply"]]
    done = [e for e in examples if e["reply"]]
    return _page("admin/outreach_voice.html", tab="voice", open_examples=open_, done_examples=done,
                 field_max=FIELD_MAX, blank=_clean_example({}, "hypothetical"))


def _form_ok() -> bool:
    if not _validate_csrf(request.form.get("csrf_token")):
        flash("Your session expired. Try again.", "error")
        return False
    return True


@bp.post("/admin/outreach/voice")
@admin_required
def voice_add():
    if _form_ok():
        example = _clean_example(request.form, "hypothetical")
        example["id"] = uuid4().hex
        if not example["ceo_message"]:
            flash("Add the CEO's message.", "error")
        else:
            save_examples(load_examples() + [example])
            flash(f"Added “{example['title'] or 'example'}”.", "success")
    return redirect(url_for("outreach.voice"))


@bp.post("/admin/outreach/voice/<example_id>")
@admin_required
def voice_save(example_id: str):
    if _form_ok():
        examples = load_examples()
        for i, old in enumerate(examples):
            if old["id"] == example_id:
                new = _clean_example({**old, **request.form.to_dict(), "id": example_id, "updated_at": _now()}, old["source"])
                if not new["ceo_message"]:
                    flash("The CEO's message can't be empty.", "error")
                    break
                examples[i] = new
                save_examples(examples)
                flash(f"Saved “{new['title'] or 'example'}”.", "success")
                return redirect(url_for("outreach.voice") + f"#ex-{example_id}")
        else:
            flash("That example is gone.", "error")
    return redirect(url_for("outreach.voice"))


@bp.post("/admin/outreach/voice/<example_id>/delete")
@admin_required
def voice_delete(example_id: str):
    if _form_ok():
        examples = load_examples()
        kept = [e for e in examples if e["id"] != example_id]
        if len(kept) < len(examples):
            save_examples(kept)
            flash("Deleted.", "success")
    return redirect(url_for("outreach.voice"))


# ---- the routine's sync ----------------------------------------------------------------------

@bp.post("/admin/outreach/sync")
def sync():
    """The Mac's routine, with OUTREACH_SYNC_TOKEN: stores its files, merges the examples it
    learned, and answers with every example (what the Voice tab holds)."""
    token = current_app.config.get("OUTREACH_SYNC_TOKEN")
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token or not secrets.compare_digest(given, token):
        abort(404)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="send JSON"), 400

    leads_csv = body.get("leads_csv")
    if leads_csv is not None:
        header = next(csv.reader(io.StringIO(leads_csv)), [])
        if not {"name", "status", "company"} <= set(header):
            return jsonify(error="leads_csv has no name/company/status header"), 400
        _write("leads.csv", leads_csv)
    if isinstance(body.get("bounces_csv"), str):
        _write("bounces.csv", body["bounces_csv"])
    if isinstance(body.get("stats"), dict):
        _write("stats.json", json.dumps(body["stats"]))

    examples = load_examples()
    if not examples and isinstance(body.get("seed_examples"), list):
        examples = [_clean_example(e, "hypothetical") for e in body["seed_examples"] if isinstance(e, dict)]
    known = {e["id"] for e in examples}
    for raw in body.get("new_examples") or []:
        if isinstance(raw, dict) and raw.get("ceo_message"):
            example = _clean_example(raw, "real")
            if example["id"] not in known:
                examples.append(example)
                known.add(example["id"])
    save_examples(examples)
    _write("synced_at", _now())
    return jsonify(examples=examples, synced_at=_read("synced_at"))
