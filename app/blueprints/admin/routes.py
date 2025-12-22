import hashlib
import secrets
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import current_app, flash, redirect, render_template, request, session, url_for
from PIL import Image, ImageOps
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from . import bp
from ...portfolio import get_portfolio_store


def _admin_configured() -> bool:
    cfg = current_app.config
    username = cfg.get("ADMIN_USERNAME")
    password_hash = cfg.get("ADMIN_PASSWORD_HASH")
    password = cfg.get("ADMIN_PASSWORD")
    return bool(username and (password_hash or password))


def _verify_password(password: str) -> bool:
    cfg = current_app.config
    password_hash = cfg.get("ADMIN_PASSWORD_HASH")
    password_plain = cfg.get("ADMIN_PASSWORD")
    if password_hash:
        return check_password_hash(password_hash, password)
    if password_plain:
        return secrets.compare_digest(password_plain, password)
    return False


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _validate_csrf(token: str) -> bool:
    if not token:
        return False
    session_token = session.get("csrf_token")
    return bool(session_token and secrets.compare_digest(session_token, token))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@bp.app_errorhandler(RequestEntityTooLarge)
def handle_request_too_large(_error):
    max_bytes = current_app.config.get("MAX_CONTENT_LENGTH") or 0
    max_mb = int(max_bytes / (1024 * 1024)) if max_bytes else 0
    message = "Upload too large."
    if max_mb:
        message = f"Upload too large. Max file size is {max_mb} MB."
    flash(message, "error")
    return redirect(request.referrer or url_for("admin.portfolio_list"))


@bp.get("/")
@admin_required
def dashboard():
    return redirect(url_for("admin.portfolio_list"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_authenticated"):
        return redirect(url_for("admin.portfolio_list"))

    if request.method == "GET" and not _admin_configured():
        flash("Admin credentials are not configured.", "error")

    if request.method == "POST":
        if not _admin_configured():
            flash("Admin credentials are not configured.", "error")
            return render_template("admin/login.html", csrf_token=_csrf_token())

        if not _validate_csrf(request.form.get("csrf_token")):
            flash("Invalid or missing CSRF token.", "error")
            return render_template("admin/login.html", csrf_token=_csrf_token())

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username != current_app.config.get("ADMIN_USERNAME") or not _verify_password(password):
            flash("Invalid username or password.", "error")
            return render_template("admin/login.html", csrf_token=_csrf_token())

        session["admin_authenticated"] = True
        session["admin_username"] = username

        next_url = request.args.get("next")
        return redirect(next_url or url_for("admin.portfolio_list"))

    return render_template("admin/login.html", csrf_token=_csrf_token())


@bp.post("/logout")
@admin_required
def logout():
    if not _validate_csrf(request.form.get("csrf_token")):
        flash("Invalid or missing CSRF token.", "error")
        return redirect(url_for("admin.portfolio_list"))

    session.pop("admin_authenticated", None)
    session.pop("admin_username", None)
    session.pop("csrf_token", None)
    return redirect(url_for("admin.login"))


@bp.get("/portfolio")
@admin_required
def portfolio_list():
    store = get_portfolio_store()
    items = store.list_items(include_unpublished=True)
    return render_template("admin/portfolio_list.html", items=items, csrf_token=_csrf_token())


@bp.route("/portfolio/new", methods=["GET", "POST"])
@admin_required
def portfolio_new():
    if request.method == "POST":
        if not _validate_csrf(request.form.get("csrf_token")):
            flash("Invalid or missing CSRF token.", "error")
            return redirect(url_for("admin.portfolio_new"))

        payload, error = _item_payload_from_form(request)
        if error:
            flash(error, "error")
            return render_template(
                "admin/portfolio_form.html",
                item=payload,
                csrf_token=_csrf_token(),
                form_action=url_for("admin.portfolio_new"),
                form_title="Add Portfolio Item",
                submit_label="Create",
                **_upload_context(),
            )

        store = get_portfolio_store()
        store.create_item(payload)
        flash("Portfolio item created.", "success")
        return redirect(url_for("admin.portfolio_list"))

    empty_item = _empty_item_defaults()
    return render_template(
        "admin/portfolio_form.html",
        item=empty_item,
        csrf_token=_csrf_token(),
        form_action=url_for("admin.portfolio_new"),
        form_title="Add Portfolio Item",
        submit_label="Create",
        **_upload_context(),
    )


@bp.route("/portfolio/<item_id>/edit", methods=["GET", "POST"])
@admin_required
def portfolio_edit(item_id: str):
    store = get_portfolio_store()
    existing = store.get_item(item_id)
    if not existing:
        flash("Portfolio item not found.", "error")
        return redirect(url_for("admin.portfolio_list"))

    if request.method == "POST":
        if not _validate_csrf(request.form.get("csrf_token")):
            flash("Invalid or missing CSRF token.", "error")
            return redirect(url_for("admin.portfolio_edit", item_id=item_id))

        payload, error = _item_payload_from_form(request)
        if error:
            flash(error, "error")
            payload["id"] = item_id
            return render_template(
                "admin/portfolio_form.html",
                item=payload,
                csrf_token=_csrf_token(),
                form_action=url_for("admin.portfolio_edit", item_id=item_id),
                form_title="Edit Portfolio Item",
                submit_label="Save",
                **_upload_context(),
            )

        store.update_item(item_id, payload)
        flash("Portfolio item updated.", "success")
        return redirect(url_for("admin.portfolio_list"))

    return render_template(
        "admin/portfolio_form.html",
        item=existing,
        csrf_token=_csrf_token(),
        form_action=url_for("admin.portfolio_edit", item_id=item_id),
        form_title="Edit Portfolio Item",
        submit_label="Save",
        **_upload_context(),
    )


@bp.post("/portfolio/<item_id>/delete")
@admin_required
def portfolio_delete(item_id: str):
    if not _validate_csrf(request.form.get("csrf_token")):
        flash("Invalid or missing CSRF token.", "error")
        return redirect(url_for("admin.portfolio_list"))

    store = get_portfolio_store()
    if not store.delete_item(item_id):
        flash("Portfolio item not found.", "error")
        return redirect(url_for("admin.portfolio_list"))

    flash("Portfolio item deleted.", "success")
    return redirect(url_for("admin.portfolio_list"))


def _empty_item_defaults() -> dict:
    return {
        "title": "",
        "short_desc": "",
        "long_desc": "",
        "image_full": "",
        "image_thumb": "",
        "image_alt": "",
        "sort_order": "",
        "is_published": True,
    }


def _item_payload_from_form(req) -> tuple[dict, str | None]:
    form = req.form
    files = req.files
    auto_thumbnail = form.get("auto_thumbnail") == "on"
    payload = {
        "title": form.get("title", "").strip(),
        "short_desc": form.get("short_desc", "").strip(),
        "long_desc": form.get("long_desc", "").strip(),
        "image_full": form.get("image_full", "").strip(),
        "image_thumb": form.get("image_thumb", "").strip(),
        "image_alt": form.get("image_alt", "").strip(),
        "is_published": form.get("is_published") == "on",
    }
    errors: list[str] = []

    full_upload = files.get("image_full_file")
    thumb_upload = files.get("image_thumb_file")

    if payload["title"] == "":
        errors.append("Title is required.")
    if payload["short_desc"] == "":
        errors.append("Card description is required.")
    if payload["long_desc"] == "":
        errors.append("Lightbox description is required.")
    if payload["image_alt"] == "":
        errors.append("Image alt text is required.")

    sort_order_raw = form.get("sort_order", "").strip()
    if sort_order_raw:
        try:
            payload["sort_order"] = int(sort_order_raw)
        except ValueError:
            errors.append("Sort order must be a number.")

    if full_upload and full_upload.filename:
        try:
            payload["image_full"] = _save_image_upload(full_upload, Path(current_app.config["UPLOADS_DIR"]))
        except ValueError as exc:
            errors.append(str(exc))
    elif not payload["image_full"]:
        errors.append("Full image is required.")
    else:
        path_error = _validate_relative_path(payload["image_full"], "Full image path")
        if path_error:
            errors.append(path_error)
        else:
            ext_error = _validate_extension(payload["image_full"], "Full image path")
            if ext_error:
                errors.append(ext_error)

    if auto_thumbnail:
        if full_upload and payload.get("image_full"):
            thumb_path, thumb_error = _generate_thumbnail(payload["image_full"])
            if thumb_error:
                errors.append(thumb_error)
            else:
                payload["image_thumb"] = thumb_path
        elif payload.get("image_thumb"):
            path_error = _validate_relative_path(payload["image_thumb"], "Thumbnail path")
            if path_error:
                errors.append(path_error)
            else:
                ext_error = _validate_extension(payload["image_thumb"], "Thumbnail path")
                if ext_error:
                    errors.append(ext_error)
        else:
            thumb_path, thumb_error = _generate_thumbnail(payload.get("image_full", ""))
            if thumb_error:
                errors.append(thumb_error)
            else:
                payload["image_thumb"] = thumb_path
    else:
        if thumb_upload and thumb_upload.filename:
            try:
                payload["image_thumb"] = _save_image_upload(thumb_upload, Path(current_app.config["UPLOADS_DIR"]))
            except ValueError as exc:
                errors.append(str(exc))
        elif not payload["image_thumb"]:
            errors.append("Thumbnail image is required when auto thumbnail is off.")
        else:
            path_error = _validate_relative_path(payload["image_thumb"], "Thumbnail path")
            if path_error:
                errors.append(path_error)
            else:
                ext_error = _validate_extension(payload["image_thumb"], "Thumbnail path")
                if ext_error:
                    errors.append(ext_error)

    if errors:
        return payload, " ".join(errors)

    return payload, None


def _upload_context() -> dict:
    max_bytes = current_app.config.get("MAX_CONTENT_LENGTH") or 0
    max_mb = int(max_bytes / (1024 * 1024)) if max_bytes else 0
    allowed = sorted(current_app.config.get("ALLOWED_IMAGE_EXTENSIONS", []))
    return {
        "max_upload_mb": max_mb,
        "allowed_extensions": allowed,
        "auto_thumbnail_default": True,
    }


def _save_image_upload(file_storage, dest_dir: Path) -> str:
    filename = secure_filename(file_storage.filename or "")
    if not filename or "." not in filename:
        raise ValueError("Uploaded file must have a valid filename.")

    ext = filename.rsplit(".", 1)[1].lower()
    allowed = current_app.config.get("ALLOWED_IMAGE_EXTENSIONS", set())
    if ext not in allowed:
        raise ValueError(f"Only {', '.join(sorted(allowed))} files are allowed.")

    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as img:
            img.verify()
    except Exception as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc
    finally:
        file_storage.stream.seek(0)

    dest_dir.mkdir(parents=True, exist_ok=True)
    base_name = Path(filename).stem
    unique_name = f"{base_name}-{uuid4().hex}.{ext}"
    dest_path = dest_dir / unique_name
    file_storage.save(dest_path)
    return _relative_static_path(dest_path)


def _generate_thumbnail(image_full_path: str) -> tuple[str | None, str | None]:
    if not image_full_path:
        return None, "Full image is required to generate a thumbnail."

    src_path = _resolve_static_path(image_full_path)
    if not src_path:
        return None, "Auto thumbnail requires a local static full image path."

    allowed = current_app.config.get("ALLOWED_IMAGE_EXTENSIONS", set())
    ext = src_path.suffix.lower().lstrip(".")
    if ext not in allowed:
        return None, "Full image must be a supported format to auto-generate thumbnails."

    thumbs_dir = Path(current_app.config["UPLOADS_THUMBS_DIR"])
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    rel_path = src_path.relative_to(Path(current_app.static_folder).resolve()).as_posix()
    suffix = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:8]
    dest_name = f"{src_path.stem}-thumb-{suffix}.{ext}"
    dest_path = thumbs_dir / dest_name

    try:
        with Image.open(src_path) as img:
            thumb = ImageOps.fit(img, (640, 360), method=Image.LANCZOS)
            if dest_path.suffix.lower() in {".jpg", ".jpeg"}:
                thumb = thumb.convert("RGB")
            thumb.save(dest_path)
    except Exception:
        return None, "Failed to generate thumbnail."

    return _relative_static_path(dest_path), None


def _relative_static_path(path: Path) -> str:
    static_root = Path(current_app.static_folder).resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(static_root):
        raise ValueError("Upload path must live inside the static folder.")
    return resolved.relative_to(static_root).as_posix()


def _resolve_static_path(relative_path: str) -> Path | None:
    if not relative_path or relative_path.startswith("/") or relative_path.startswith("http"):
        return None
    static_root = Path(current_app.static_folder).resolve()
    candidate = (static_root / relative_path).resolve()
    if not candidate.is_relative_to(static_root):
        return None
    if not candidate.exists():
        return None
    return candidate


def _validate_relative_path(value: str, label: str) -> str | None:
    if not value:
        return None
    if value.startswith("/") or value.startswith("http://") or value.startswith("https://"):
        return f"{label} must be relative to /static."
    if ".." in Path(value).parts:
        return f"{label} must not include '..'."
    return None


def _validate_extension(value: str, label: str) -> str | None:
    ext = Path(value).suffix.lower().lstrip(".")
    allowed = current_app.config.get("ALLOWED_IMAGE_EXTENSIONS", set())
    if ext not in allowed:
        return f"{label} must end with {', '.join(sorted(allowed))}."
    return None
