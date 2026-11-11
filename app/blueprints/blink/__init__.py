"""/blink: the web home of Blink, my iMessage app for photos that disappear once they're opened.

App Store Connect points at /blink/privacy (privacy policy) and /blink/support (support URL), so
keep both addresses stable. The app's code lives in the private Jerenemy/blink repo."""
from flask import Blueprint, current_app, render_template, url_for

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
    response = current_app.make_response(render_template('blink/open.html', tabs=tabs(None)))
    response.headers['X-Robots-Tag'] = 'noindex'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@bp.get('/blink/privacy', strict_slashes=False)
def privacy():
    return render_template('blink/privacy.html', tabs=tabs('blink.privacy'))
