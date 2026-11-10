"""/scic: the hub for my work at Wesleyan's Scientific Computing and Informatics Center.

Its pages live in their own blueprints (the Clash table is clash_royale's /scic/clash); add one to
PAGES and it appears in the hub's list and in the tabs every SCIC page shows.

/scic/reviews is this blueprint's own: anyone can rate my tutoring out of five stars and write a
few words. Reviews go up at once; /admin/reviews takes one down. They live in SQLite under
instance/ (SCIC_REVIEWS_DATABASE_PATH), untracked like the site's other stores."""
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from ..admin.routes import _csrf_token, _validate_csrf, admin_required

bp = Blueprint('scic', __name__)

# (endpoint, name, one line): in the order the hub lists them.
PAGES = [
    ('clash.page', 'Clash', "Our friendly Clash Royale battles: who's on top, and who beats whom."),
    ('scic.reviews', 'Reviews', 'Rate my tutoring out of five stars and say how it went.'),
]

NAME_MAX, TEXT_MAX = 60, 2000
DAILY_LIMIT = 3  # reviews one address may post in 24 hours


def tabs(current):
    """The row of tabs at the top of every SCIC page: the hub first, then each page."""
    return [(url_for('scic.hub'), 'SCIC', current == 'scic.hub')] + [
        (url_for(endpoint), name, current == endpoint) for endpoint, name, _ in PAGES]


@bp.app_context_processor
def scic_nav():
    return {'scic_tabs': tabs}


@bp.get('/scic', strict_slashes=False)
def hub():
    pages = [{'href': url_for(endpoint), 'name': name, 'line': line} for endpoint, name, line in PAGES]
    return render_template('scic/hub.html', pages=pages)


# ---------------------------------------------------------------- reviews

class ReviewError(ValueError):
    pass


@contextmanager
def database():
    path = Path(current_app.config['SCIC_REVIEWS_DATABASE_PATH'])
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL
            )""")
            yield connection
    finally:
        connection.close()


def clean(form):
    """The review a form describes, checked: (name, rating, text), or ReviewError saying what to fix."""
    try:
        rating = int(form.get('rating', ''))
    except ValueError:
        rating = 0
    if not 1 <= rating <= 5:
        raise ReviewError('Pick a rating from one to five stars.')
    name = ' '.join(form.get('name', '').split())
    text = form.get('text', '').replace('\r\n', '\n').strip()
    if len(name) > NAME_MAX:
        raise ReviewError(f'Keep your name under {NAME_MAX} characters.')
    if not text:
        raise ReviewError('Write a few words about how it went.')
    if len(text) > TEXT_MAX:
        raise ReviewError(f'Keep the review under {TEXT_MAX:,} characters.')
    return name, rating, text


def source():
    """Who posted, as a salted hash of their address: enough to count, never the address itself."""
    from ..clash_royale import client_ip
    salt = current_app.config.get('SECRET_KEY') or ''
    return hashlib.sha256(f'{salt}:{client_ip()}'.encode()).hexdigest()


def summary(rows):
    count = len(rows)
    average = round(sum(r['rating'] for r in rows) / count, 1) if count else None
    spread = [{'stars': n, 'count': sum(1 for r in rows if r['rating'] == n)} for n in range(5, 0, -1)]
    for row in spread:
        row['share'] = round(100 * row['count'] / count) if count else 0
    return {'count': count, 'average': average, 'spread': spread}


@bp.after_request
def fresh_response(response):
    if request.endpoint in ('scic.reviews', 'scic.review_admin'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/scic/reviews', methods=['GET', 'POST'], strict_slashes=False)
def reviews():
    error, form, status = None, {}, 200
    if request.method == 'POST':
        form = request.form
        if not _validate_csrf(form.get('csrf_token')):
            error, status = 'Your form expired. Reload the page and try again.', 400
        elif form.get('website', ''):
            # The honeypot: a bot filled the hidden field. Tell it all went well.
            session['review_posted'] = True
            return redirect(url_for('scic.reviews', _anchor='write'), code=303)
        else:
            try:
                name, rating, text = clean(form)
                who = source()
                since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
                with database() as db:
                    recent = db.execute('SELECT COUNT(*) FROM reviews WHERE source=? AND created_at>?',
                                        (who, since)).fetchone()[0]
                    if recent >= DAILY_LIMIT:
                        raise ReviewError("You've posted a few reviews today. Try again tomorrow.")
                    db.execute('INSERT INTO reviews (name, rating, text, created_at, source) VALUES (?,?,?,?,?)',
                               (name, rating, text, datetime.now(timezone.utc).isoformat(), who))
            except ReviewError as exc:
                error, status = str(exc), 400
            except (sqlite3.Error, OSError):
                current_app.logger.exception('SCIC reviews storage unavailable')
                error, status = "We couldn't save your review. Please try again.", 503
            else:
                session['review_posted'] = True
                return redirect(url_for('scic.reviews', _anchor='write'), code=303)
    try:
        with database() as db:
            rows = db.execute('SELECT id, name, rating, text, created_at FROM reviews ORDER BY id DESC').fetchall()
    except (sqlite3.Error, OSError):
        current_app.logger.exception('SCIC reviews storage unavailable')
        rows = []
    posted = session.pop('review_posted', False) if request.method == 'GET' else False
    return render_template('scic/reviews.html', reviews=rows, summary=summary(rows), csrf_token=_csrf_token(),
                           error=error, form=form, posted=posted, name_max=NAME_MAX, text_max=TEXT_MAX), status


@bp.get('/admin/reviews')
@admin_required
def review_admin():
    with database() as db:
        rows = db.execute('SELECT id, name, rating, text, created_at FROM reviews ORDER BY id DESC').fetchall()
    return render_template('admin/reviews.html', reviews=rows, csrf_token=_csrf_token())


@bp.post('/admin/reviews/<int:review_id>/delete')
@admin_required
def review_delete(review_id):
    if not _validate_csrf(request.form.get('csrf_token')):
        flash('Your form expired. Reload the page and try again.', 'error')
    else:
        with database() as db:
            gone = db.execute('DELETE FROM reviews WHERE id=?', (review_id,)).rowcount
        flash('Review removed.' if gone else 'That review was already gone.', 'success' if gone else 'error')
    return redirect(url_for('scic.review_admin'), code=303)
