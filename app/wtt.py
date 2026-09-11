"""Small, private email signup store and its public/admin views."""
import csv
import io
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import click
from flask import Blueprint, Response, current_app, redirect, render_template, request, session, url_for
from flask.cli import with_appcontext

from .blueprints.admin.routes import _csrf_token, _validate_csrf, admin_required

bp = Blueprint("wtt", __name__)
_LOCAL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+\Z")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def normalize_email(value):
    email = value.strip().lower()
    if len(email) > 254 or email.count("@") != 1:
        raise ValueError("Enter a valid email address.")
    local, domain = email.split("@")
    if (not _LOCAL.fullmatch(local) or len(local) > 64 or local.startswith(".")
            or local.endswith(".") or ".." in local or "." not in domain
            or not all(_LABEL.fullmatch(label) for label in domain.split("."))):
        raise ValueError("Enter a valid email address.")
    return email


@contextmanager
def database():
    path = Path(current_app.config["WTT_DATABASE_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS wtt_signups (
                email TEXT NOT NULL COLLATE NOCASE PRIMARY KEY,
                created_at TEXT NOT NULL
            )""")
            yield connection
    finally:
        connection.close()


@click.command("init-wtt-db")
@with_appcontext
def init_db_command():
    """Create the signup table without deleting existing entries."""
    with database():
        pass
    click.echo("WTT database initialized.")


@bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@bp.route("/wtt", methods=["GET", "POST"], strict_slashes=False)
def signup():
    error, email, status = None, "", 200
    if request.method == "POST":
        email = request.form.get("email", "")
        if not _validate_csrf(request.form.get("csrf_token")):
            error, status = "Your form expired. Please try again.", 400
        elif request.form.get("website", ""):
            session["wtt_success"] = True
            return redirect(url_for("wtt.signup"), code=303)
        else:
            try:
                normalized = normalize_email(email)
                with database() as connection:
                    connection.execute(
                        "INSERT INTO wtt_signups (email, created_at) VALUES (?, ?) "
                        "ON CONFLICT(email) DO NOTHING",
                        (normalized, datetime.now(timezone.utc).isoformat()),
                    )
            except ValueError as exc:
                error, status = str(exc), 400
            except (sqlite3.Error, OSError):
                current_app.logger.error("WTT signup storage unavailable")
                error, status = "We couldn't save your email. Please try again.", 503
            else:
                session["wtt_success"] = True
                return redirect(url_for("wtt.signup"), code=303)
    success = session.pop("wtt_success", False) if request.method == "GET" else False
    return render_template("wtt.html", csrf_token=_csrf_token(), email=email,
                           error=error, success=success), status


@bp.get("/admin/wtt")
@admin_required
def signups():
    with database() as connection:
        rows = connection.execute("SELECT email, created_at FROM wtt_signups ORDER BY created_at DESC").fetchall()
    return render_template("admin/wtt.html", signups=rows)


@bp.get("/admin/wtt/export.csv")
@admin_required
def export():
    with database() as connection:
        rows = connection.execute("SELECT email, created_at FROM wtt_signups ORDER BY created_at DESC").fetchall()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["email", "created_at"])
    for row in rows:
        # Keep spreadsheet applications from interpreting an email as a formula.
        email = row["email"]
        writer.writerow(["'" + email if email.startswith(("=", "+", "-", "@")) else email, row["created_at"]])
    return Response(output.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": 'attachment; filename="wtt-signups.csv"',
    })
