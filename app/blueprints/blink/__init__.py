"""/blink: the web home of Blink, my iMessage app for photos that disappear once they're opened.

App Store Connect points at /blink/privacy (privacy policy) and /blink/support (support URL), so
keep both addresses stable. The app's code lives in the private Jerenemy/blink repo."""
import base64
import json
import os
import re
import time

from flask import Blueprint, current_app, jsonify, render_template, request, url_for

from . import cloudkit

bp = Blueprint('blink', __name__)

# (endpoint, tab name): in tab order.
PAGES = [
    ('blink.about', 'Blink'),
    ('blink.support', 'Support'),
    ('blink.privacy', 'Privacy'),
]


def tabs(current):
    return [(url_for(endpoint), name, endpoint == current) for endpoint, name in PAGES]


@bp.get('/blink', strict_slashes=False)
def about():
    return render_template('blink/about.html', tabs=tabs('blink.about'))


@bp.get('/blink/support', strict_slashes=False)
def support():
    return render_template('blink/support.html', tabs=tabs('blink.support'))


@bp.get('/blink/v', strict_slashes=False)
def open_link():
    """Where a Blink's link lands if someone opens it outside Messages. The photo's key is in the
    link's #fragment, which browsers never send, so this page never sees it."""
    response = current_app.make_response(render_template(
        'blink/open.html', tabs=tabs(None), app_store_id=current_app.config.get('BLINK_APP_STORE_ID')))
    response.headers['X-Robots-Tag'] = 'noindex'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


SNAP_ID = re.compile(r'^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$')
REASONS = {'nudity', 'harassment', 'violence', 'spam', 'other'}


@bp.get('/blink/api/snap/<snap_id>')
def snap(snap_id):
    """The encrypted photo or video for the App Clip, which can't use CloudKit itself. Ciphertext
    only: the key travels in the link's #fragment, which never reaches this server."""
    if not SNAP_ID.match(snap_id):
        return jsonify(error='bad id'), 400
    try:
        data = cloudkit.fetch_snap(snap_id)
    except cloudkit.Gone:
        return jsonify(error='gone'), 410
    except cloudkit.NotConfigured:
        return jsonify(error='not configured'), 503
    except Exception:
        current_app.logger.exception('Blink fetch failed')
        return jsonify(error='failed'), 502
    response = current_app.response_class(data, mimetype='application/octet-stream')
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/blink/api/viewed')
def viewed():
    """The App Clip opened a photo: delete it. App Clips can read CloudKit but not write to it, so the
    clip asks here. Knowing a photo's ID is enough, the same as for the app, which can delete any Snap."""
    snap_id = (request.get_json(silent=True) or {}).get('id', '')
    if not SNAP_ID.match(snap_id):
        return jsonify(error='bad id'), 400
    try:
        gone = cloudkit.delete_snap(snap_id)
    except cloudkit.NotConfigured:
        current_app.logger.error('Blink delete skipped: CloudKit key not configured')
        return jsonify(error='not configured'), 503
    except Exception:
        current_app.logger.exception('Blink delete failed')
        return jsonify(error='failed'), 502
    return ('', 204) if gone else (jsonify(error='failed'), 502)


@bp.post('/blink/api/report')
def report():
    """A report from the App Clip (which can't write the CloudKit Report record the app uses).
    Kept in instance/blink_reports for review, with the photo."""
    data = request.get_json(silent=True) or {}
    snap_id, reason = data.get('id', ''), data.get('reason', '')
    if not SNAP_ID.match(snap_id) or reason not in REASONS:
        return jsonify(error='bad report'), 400
    try:
        photo = base64.b64decode(data.get('photo', ''), validate=True)
    except ValueError:
        return jsonify(error='bad photo'), 400
    if len(photo) > 4 * 1024 * 1024:
        return jsonify(error='photo too large'), 413
    folder = os.path.join(current_app.config['BLINK_REPORTS_DIR'], f"{int(time.time())}-{snap_id}")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'report.json'), 'w') as f:
        json.dump({'id': snap_id, 'reason': reason, 'received': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}, f)
    if photo:
        with open(os.path.join(folder, 'photo.jpg'), 'wb') as f:
            f.write(photo)
    current_app.logger.warning('Blink report %s (%s) saved to %s', snap_id, reason, folder)
    return '', 204


@bp.get('/blink/privacy', strict_slashes=False)
def privacy():
    return render_template('blink/privacy.html', tabs=tabs('blink.privacy'))
