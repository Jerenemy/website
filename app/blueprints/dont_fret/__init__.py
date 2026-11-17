"""/dont-fret: Don't Fret, my Mac app that teaches guitar through real songs.

/dont-fret/listening-test is a blind listening test of the app's guitar sound, after MUSHRA
(ITU-R BS.1534): each piece is the same eight seconds played several ways (the studio recording,
the new and old guitar engines, and the recording low-passed at 3.5 kHz as a low anchor), and
listeners rate how real each clip sounds. The clips and their manifest are built by
scripts/soundlab/listening_test.py in the Don't Fret repo and live in
static/dont-fret/listening-test/. Which clip is which is in instance/dont_fret_listening_key.json,
which is never committed (this repository is public) and never served: copy it to the server with
the clips (see the README). Answers go to an SQLite file in instance/ (untracked, like the other
stores); the results are at /admin/dont-fret/listening-test."""
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, url_for

from ..admin.routes import admin_required

bp = Blueprint('dont_fret', __name__)

STATIC = 'dont-fret/listening-test'
LISTENER = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
EXPERIENCE = ('none', 'some', 'regular', 'pro')
PLAYBACK = ('headphones', 'speakers', 'laptop')
MAX_BODY = 16 * 1024    # one listener's answers are about 2 KB
NEW_PER_DAY = 20        # new listeners one network may start in 24 hours
CONDITIONS = [('real', 'Real recording'), ('new', 'New engine'), ('old', 'Old engine'), ('anchor', '3.5 kHz anchor')]
BANDS = ['Bad', 'Poor', 'Fair', 'Good', 'Excellent']
# two-sided 95% Student t for 1-20 degrees of freedom
T95 = [12.71, 4.30, 3.18, 2.78, 2.57, 2.45, 2.36, 2.31, 2.26, 2.23, 2.20, 2.18, 2.16, 2.14, 2.13, 2.12, 2.11, 2.10, 2.09, 2.09]

_cache = {}


def _load(path):
    """A JSON file, read again only when it changes on disk."""
    path = Path(path)
    stamp = path.stat().st_mtime
    hit = _cache.get(path)
    if not hit or hit[0] != stamp:
        hit = (stamp, json.loads(path.read_text()))
        _cache[path] = hit
    return hit[1]


def manifest():
    return _load(Path(current_app.static_folder) / STATIC / 'manifest.json')


def answer_key():
    """clip file → condition, or None when the key isn't on this server yet. Server only."""
    path = Path(current_app.config['DONT_FRET_LISTENING_KEY_PATH'])
    return _load(path) if path.is_file() else None


def trials():
    return {t['id']: t for t in manifest()['trials']}


@contextmanager
def database():
    path = Path(current_app.config['DONT_FRET_LISTENING_DATABASE_PATH'])
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS answers (
                listener TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                info TEXT NOT NULL,
                letters TEXT NOT NULL,
                ratings TEXT NOT NULL,
                finished INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )''')
            yield connection
    finally:
        connection.close()


def source():
    """The listener's network, as a salted hash of the address: enough to count, never the address."""
    from ..clash_royale import client_ip
    salt = current_app.config.get('SECRET_KEY') or ''
    return hashlib.sha256(f'{salt}:dont-fret:{client_ip()}'.encode()).hexdigest()


def clean(data):
    """Checks one listener's answers against the manifest. Raises ValueError, saying why."""
    if not isinstance(data, dict):
        raise ValueError('expected an object')
    listener = data.get('listener')
    if not isinstance(listener, str) or not LISTENER.match(listener):
        raise ValueError('bad listener')
    info = data.get('info') or {}
    if not isinstance(info, dict):
        raise ValueError('bad info')
    experience, playback = info.get('experience') or '', info.get('playback') or ''
    if experience not in ('',) + EXPERIENCE or playback not in ('',) + PLAYBACK:
        raise ValueError('bad info')
    known = trials()
    letters, ratings = data.get('letters') or {}, data.get('ratings') or {}
    if not isinstance(letters, dict) or not isinstance(ratings, dict):
        raise ValueError('bad answers')
    for tid, files in letters.items():
        if tid not in known or not isinstance(files, list) or sorted(files) != sorted(s['file'] for s in known[tid]['stimuli']):
            raise ValueError('bad order')
    clean_ratings = {}
    for tid, scores in ratings.items():
        if tid not in known or not isinstance(scores, dict):
            raise ValueError('bad piece')
        files = {s['file'] for s in known[tid]['stimuli']}
        for file, score in scores.items():
            if file not in files or isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
                raise ValueError('bad rating')
        if scores:
            clean_ratings[tid] = scores
    finished = bool(data.get('finished'))
    if finished and set(clean_ratings) != set(known):
        raise ValueError('not finished')
    return listener, {'experience': experience, 'playback': playback}, letters, clean_ratings, finished


@bp.after_request
def headers(response):
    response.headers['X-Robots-Tag'] = 'noindex'
    if request.method != 'GET' or request.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/dont-fret', strict_slashes=False)
def home():
    return redirect(url_for('dont_fret.listening_test'))


@bp.get('/dont-fret/listening-test', strict_slashes=False)
def listening_test():
    m = manifest()
    return render_template('dont_fret/listening_test.html',
                           manifest_url=url_for('static', filename=f'{STATIC}/manifest.json'),
                           pieces=len(m['trials']), seconds=round(m['seconds']))


@bp.post('/dont-fret/listening-test/answers')
def save_answers():
    """One listener's answers so far (the page posts after every piece). Creates or replaces."""
    if (request.content_length or 0) > MAX_BODY:
        return jsonify(error='too large'), 413
    try:
        listener, info, letters, ratings, finished = clean(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    now = datetime.now(timezone.utc)
    try:
        with database() as db:
            row = db.execute('SELECT 1 FROM answers WHERE listener = ?', (listener,)).fetchone()
            if row is None:
                who = source()
                recent = db.execute('SELECT COUNT(*) FROM answers WHERE source = ? AND created_at > ?',
                                    (who, (now - timedelta(days=1)).isoformat())).fetchone()[0]
                if recent >= NEW_PER_DAY:
                    return jsonify(error='limit'), 429
                db.execute('INSERT INTO answers VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                           (listener, who, json.dumps(info), json.dumps(letters), json.dumps(ratings),
                            int(finished), now.isoformat(), now.isoformat()))
            else:
                db.execute('UPDATE answers SET info = ?, letters = ?, ratings = ?, finished = ?, updated_at = ? '
                           'WHERE listener = ?',
                           (json.dumps(info), json.dumps(letters), json.dumps(ratings), int(finished),
                            now.isoformat(), listener))
    except (sqlite3.Error, OSError):
        current_app.logger.error("Don't Fret listening answers unavailable")
        return jsonify(error='unavailable'), 503
    return '', 204


# ---------------------------------------------------------------- results

def stats(values):
    """Mean and the half-width of its 95% confidence interval (Student t)."""
    n = len(values)
    if not n:
        return {'n': 0, 'mean': None, 'ci': None}
    mean = sum(values) / n
    if n == 1:
        return {'n': 1, 'mean': mean, 'ci': 0.0}
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    t = T95[n - 2] if n - 1 <= len(T95) else (2.03 if n - 1 <= 40 else 1.98)
    return {'n': n, 'mean': mean, 'ci': t * sd / math.sqrt(n)}


def records(rows, key):
    """Every rating as (listener, piece, kind, condition, score), plus each listener's details."""
    known = trials()
    out, people = [], []
    for row in rows:
        ratings, info = json.loads(row['ratings']), json.loads(row['info'])
        mine = []
        for tid, scores in ratings.items():
            if tid not in known:
                continue
            for file, score in scores.items():
                if file in key:
                    mine.append({'listener': row['listener'], 'piece': tid, 'kind': known[tid]['kind'],
                                 'condition': key[file], 'score': score})
        # screening: the low anchor above the real recording in half or more of the studio pieces
        pieces = {}
        for r in mine:
            if r['kind'] == 'pro':
                pieces.setdefault(r['piece'], {})[r['condition']] = r['score']
        judged = [p for p in pieces.values() if 'real' in p and 'anchor' in p]
        flips = sum(p['anchor'] > p['real'] for p in judged)
        people.append({'listener': row['listener'], 'finished': bool(row['finished']), 'info': info,
                       'updated_at': row['updated_at'], 'ratings': mine,
                       'excluded': bool(judged) and flips * 2 >= len(judged)})
    return people


def paired(ratings, a, b):
    """a − b for every listener and piece that rated both."""
    pairs = {}
    for r in ratings:
        pairs.setdefault((r['listener'], r['piece']), {})[r['condition']] = r['score']
    diffs = [p[a] - p[b] for p in pairs.values() if a in p and b in p]
    s = stats(diffs)
    s['at_least'] = (sum(d >= 0 for d in diffs) / len(diffs)) if diffs else None
    return s


def summary(rows, key, everyone=False):
    people = records(rows, key)
    kept = [p for p in people if everyone or not p['excluded']]
    ratings = [r for p in kept for r in p['ratings']]

    def chart(kind, conditions):
        out = []
        for cond, label in conditions:
            s = stats([r['score'] for r in ratings if r['kind'] == kind and r['condition'] == cond])
            if s['n']:
                s['lo'], s['hi'] = max(0.0, s['mean'] - s['ci']), min(100.0, s['mean'] + s['ci'])
            out.append({'condition': cond, 'label': label, **s})
        return out

    pro = [r for r in ratings if r['kind'] == 'pro']
    app = [r for r in ratings if r['kind'] == 'app']
    pieces = []
    for t in manifest()['trials']:
        mine = [r for r in ratings if r['piece'] == t['id']]
        cells = {c: stats([r['score'] for r in mine if r['condition'] == c])['mean'] for c, _ in CONDITIONS}
        pieces.append({'label': t['label'], 'kind': t['kind'], 'cells': cells,
                       'listeners': len({r['listener'] for r in mine})})
    return {
        'listeners': len(people), 'finished': sum(p['finished'] for p in people),
        'excluded': sum(p['excluded'] for p in people),
        'studio': chart('pro', CONDITIONS), 'app': chart('app', [c for c in CONDITIONS if c[0] != 'real']),
        'new_vs_old': paired(pro, 'new', 'old'), 'new_vs_real': paired(pro, 'new', 'real'),
        'app_new_vs_old': paired(app, 'new', 'old'),
        'pieces': pieces, 'people': kept,
    }


def all_rows():
    with database() as db:
        return db.execute('SELECT * FROM answers ORDER BY created_at').fetchall()


@bp.get('/admin/dont-fret/listening-test')
@admin_required
def results():
    everyone, key = request.args.get('everyone') == '1', answer_key()
    rows = all_rows()
    return render_template('admin/dont_fret_listening.html', s=summary(rows, key, everyone) if key else None,
                           waiting=len(rows), everyone=everyone, bands=BANDS, conditions=CONDITIONS)


@bp.get('/admin/dont-fret/listening-test/ratings.csv')
@admin_required
def export():
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['listener', 'piece', 'kind', 'condition', 'score', 'experience', 'playback', 'finished', 'screened_out', 'updated_at'])
    key = answer_key()
    if not key:
        return Response('The answer key is not on this server yet.\n', status=503, mimetype='text/plain')
    for p in records(all_rows(), key):
        for r in p['ratings']:
            writer.writerow([p['listener'], r['piece'], r['kind'], r['condition'], r['score'], p['info'].get('experience', ''),
                             p['info'].get('playback', ''), int(p['finished']), int(p['excluded']), p['updated_at']])
    return Response(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': 'attachment; filename="dont-fret-listening-test.csv"',
    })
