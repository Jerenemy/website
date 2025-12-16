# Personal Website
A small Flask app for my personal site, serving static pages and a contact API that emails me via Flask-Mail.

## Features
- Home/portfolio/blog/game pages rendered with Jinja templates
- Contact endpoint posts to `/api/contact` and sends email via SMTP
- Resume served from `app/static/files/resume.pdf`
- Simple stub leaderboard at `/api/leaderboard`
- Audio-visual retrieval demo mounted at `/ear` (uses data in `ear_data/`)

## Tech Stack
- Python 3.13
- Flask 3
- Flask-Mail
- PyTorch + torchvision + torchaudio + Pillow for the ear demo
- Poetry for dependency management

## Local Setup
1) Install Poetry if you do not have it: `pipx install poetry`
2) Install dependencies:
   ```bash
   poetry install
   ```
3) Copy your mail settings into a `.env` file in the repo root (Flask will read these when running locally):
   ```bash
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=you@example.com
   MAIL_PASSWORD=app-password-here
   MAIL_DEFAULT_SENDER=you@example.com  # optional; defaults to MAIL_USERNAME
   ```

## Run the App
```bash
poetry run flask --app app:create_app run --debug
```
- The site will be available at `http://127.0.0.1:5000/`
- Contact POST endpoint: `http://127.0.0.1:5000/api/contact`
- Leaderboard GET endpoint: `http://127.0.0.1:5000/api/leaderboard`

## Project Structure
- `app/__init__.py` – Flask app factory and blueprint registration
- `app/blueprints/public` – Page routes (home, blog, game, resume)
- `app/blueprints/api` – API routes (contact, leaderboard)
- `app/templates/` – Jinja templates for pages/layout
- `app/static/` – Static assets (ensure `files/resume.pdf` exists)
- `ear_data/` – storage for the ear demo (dataset/audio, dataset/frames, pretrained_models, indexed_db.pt cache, uploads). Git-ignored by default; point `EAR_BASE_DIR` to move it elsewhere.

## Development Notes
- The contact route requires working SMTP credentials; without them it will 500.
- Adjust `MAIL_*` variables in `.env` or your shell to match your mail provider. The app loads `.env` explicitly from the project root, and `Config` will inject missing keys from `.env` into `os.environ` as a fallback (helps when supervisor/gunicorn starts with a different cwd).
- For production, set `MAIL_*` in your process manager (e.g., `environment=` in supervisor) if you prefer not to rely on `.env` file loading.
- Use `poetry run` before commands to ensure the virtualenv is active.
- The `/ear` demo reads from `ear_data/` by default (dataset, pretrained model, cache). Install the heavy deps manually (`torch`, `torchvision`, `torchaudio`, `Pillow`) and ensure the process user can read/write that folder. Override the location with `EAR_BASE_DIR=/absolute/path/to/ear_data` in your supervisor config if needed.
