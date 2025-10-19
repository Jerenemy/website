from flask import render_template
from . import bp

@bp.get("/")
def index():
    return render_template("index.html")

# # later: presentations
# @bp.get("/presentations")
# def presentations():
#     return render_template("presentations.html")

@bp.get("/game")
def game():
    return render_template("game.html")

# later: load post by slug; for now just show blank template
@bp.get("/blog")
def blog():
    return render_template("blog.html")