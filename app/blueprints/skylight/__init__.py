"""/skylight: Skylight, my Mac viewer for Markdown, notebooks, data and code.

App Store Connect points at /skylight/support (support URL) and /skylight/privacy (privacy policy),
so both must keep answering. The app's code lives in the private Jerenemy/skylight repo."""
from flask import Blueprint, render_template, url_for

bp = Blueprint('skylight', __name__)

# (endpoint, tab name): in tab order.
PAGES = [
    ('skylight.about', 'Skylight'),
    ('skylight.support', 'Support'),
    ('skylight.privacy', 'Privacy'),
]


def tabs(current):
    return [(url_for(endpoint), name, endpoint == current) for endpoint, name in PAGES]


@bp.get('/skylight', strict_slashes=False)
def about():
    return render_template('skylight/about.html', tabs=tabs('skylight.about'))


@bp.get('/skylight/support', strict_slashes=False)
def support():
    return render_template('skylight/support.html', tabs=tabs('skylight.support'))


@bp.get('/skylight/privacy', strict_slashes=False)
def privacy():
    return render_template('skylight/privacy.html', tabs=tabs('skylight.privacy'))
