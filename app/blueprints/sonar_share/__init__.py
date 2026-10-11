"""Share links for the Sonar iOS app.

Sonar shares https links like ``https://jeremyzay.com/sonar/r/<log id>``. iOS opens them
straight in the app when it is installed (universal links, declared by
``/.well-known/apple-app-site-association``); everyone else lands on a small page here that
previews the shared review, episode, show or profile and links to the App Store. The same
pages carry Open Graph tags, so pasted links unfurl with artwork in Messages, Slack, etc.

Data comes from Sonar's Supabase project (public anon key, read-only rows) and the Podcast
Index API. Both are optional: without them, or when a lookup fails, the page still renders
with an "Open in Sonar" / "Get Sonar" call to action.
"""

from flask import Blueprint

bp = Blueprint("sonar_share", __name__)

from . import routes  # noqa: E402,F401
