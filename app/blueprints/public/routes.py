from flask import render_template, send_from_directory, current_app
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

@bp.get("/resume")
def resume():
    # serves the file from static/files/
    return send_from_directory(
        current_app.static_folder + "/files",
        "resume.pdf",
        mimetype="application/pdf"
    )