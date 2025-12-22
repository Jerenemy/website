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
    
@bp.get("/poster-rl-2024")
def poster_rl_2024():
    # serves the file from static/files/
    return send_from_directory(
        current_app.static_folder + "/files",
        "poster-rl-2024.pdf",
        mimetype="application/pdf"
    )
    
@bp.get("/poster-diffusion-2025")
def poster_diffusion_2025():
    # serves the file from static/files/
    return send_from_directory(
        current_app.static_folder + "/files",
        "poster-diffusion-2025.pdf",
        mimetype="application/pdf"
    )
    
@bp.get('/zaychess')  # Ensure 'bp' matches your blueprint name (might be 'main' or 'app')
def zaychess():
    return render_template('zaychess.html')
