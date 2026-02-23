from flask import current_app, g

from .store import BlogStore


def get_blog_store() -> BlogStore:
    if "blog_store" not in g:
        g.blog_store = BlogStore(current_app.config["BLOG_POSTS_DIR"])
    return g.blog_store
