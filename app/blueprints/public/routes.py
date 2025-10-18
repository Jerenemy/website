from flask import render_template
from . import bp

@bp.get("/")
def home():
    return render_template("home.html")

@bp.get("/presentations")
def presentations():
    return render_template("presentations.html")

@bp.get("/game")
def game():
    return render_template("game.html")

@bp.get("/contact")
def contact():
    return render_template("contact.html")

@bp.get("/blog")
def blog_list():
    # later: load real posts; for now just render blank list page
    return render_template("blog_list.html")

@bp.get("/blog/<slug>")
def blog_post(slug):
    # later: load post by slug; for now just show blank template
    return render_template("blog_post.html", slug=slug)
