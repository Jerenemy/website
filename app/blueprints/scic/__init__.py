"""/scic: the hub for my work at Wesleyan's Scientific Computing and Informatics Center.

Its pages live in their own blueprints (the Clash table is clash_royale's /scic/clash); add one to
PAGES and it appears in the hub's list and in the tabs every SCIC page shows."""
from flask import Blueprint, render_template, url_for

bp = Blueprint('scic', __name__)

# (endpoint, name, one line): in the order the hub lists them.
PAGES = [
    ('clash.page', 'Clash', "Our friendly Clash Royale battles: who's on top, and who beats whom."),
]


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
