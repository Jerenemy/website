# Personal Website
A small Flask app for my personal site, serving static pages and a contact API that emails me via Flask-Mail.

## Features
- Home/portfolio/blog/game pages rendered with Jinja templates
- Contact endpoint posts to `/api/contact` and sends email via SMTP
- Resume served from `app/static/files/resume.pdf`
- Simple stub leaderboard at `/api/leaderboard`
- Audio-visual retrieval demo mounted at `/ear` (uses data in `ear_data/`)
- Password-protected admin area to add/edit/delete portfolio items (JSON-backed) with image uploads, preview, and delete confirmation

## Tech Stack
- Python 3.13
- Flask 3
- Flask-Mail
- PyTorch + torchvision + torchaudio + Pillow for the ear demo
- Poetry for dependency management

## Local Setup
1) Install Poetry if you do not have it: `pip install poetry`
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
4) Add admin credentials and a secret key to `.env`:
   ```bash
   SECRET_KEY=change-me-to-a-long-random-string
   ADMIN_USERNAME=admin
   # Preferred: store a hash instead of plain text
   ADMIN_PASSWORD_HASH=pbkdf2:sha256:...
   # Optional fallback for local-only use
   # ADMIN_PASSWORD=your-plain-text-password
   # Optional: move the portfolio data file
   # PORTFOLIO_DATA_PATH=/absolute/path/to/portfolio.json
   # Optional: upload limits/paths
   # MAX_UPLOAD_MB=6
   # UPLOADS_DIR=/absolute/path/to/app/static/img/uploads
   # UPLOADS_THUMBS_DIR=/absolute/path/to/app/static/img/uploads/thumbs
   ```
   Generate a password hash:
   ```bash
   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
   ```

## Run the App
```bash
poetry run flask --app app:create_app run --debug
```
- The site will be available at `http://127.0.0.1:5000/`
- Contact POST endpoint: `http://127.0.0.1:5000/api/contact`
- Leaderboard GET endpoint: `http://127.0.0.1:5000/api/leaderboard`
- Admin login: `http://127.0.0.1:5000/admin`

## Portfolio Admin
- Data lives in `app/data/portfolio.json` (configurable via `PORTFOLIO_DATA_PATH`).
- Portfolio items are rendered on the homepage from this JSON store.
- Add/edit/delete items at `/admin/portfolio`.
- Uploads are saved to `app/static/img/uploads` with auto-thumbnails in `app/static/img/uploads/thumbs`.
- Allowed upload types: `jpg`, `jpeg`, `png`, `webp` (default limit: 6 MB per file).
- Auto thumbnail generation is on by default; you can switch to manual thumbnail upload/path.
- The preview button validates required fields before showing a live card preview.
- Delete actions require confirmation.
- Each item includes:
  - `title`, `short_desc` (card text), `long_desc` (lightbox text)
  - `image_full`, `image_thumb` (paths relative to `/static`)
  - `image_alt`, `sort_order`, `is_published`
- HTML is allowed in `short_desc` and `long_desc` (e.g., links). Keep markup minimal.

## Admin Integration
- The admin UI is a standalone blueprint (`/admin`) that uses the same portfolio store as the public site.
- The public blueprint depends on the portfolio store only; it does not depend on the admin blueprint.
- The API blueprint is independent of the admin system.
- Sessions and CSRF protection rely on `SECRET_KEY`; set it in production.

### Files Added
- `app/blueprints/admin/` (routes + blueprint registration)
- `app/portfolio/` (JSON store + helpers)
- `app/templates/admin/` (login, list, form, flash partial)
- `app/static/css/pages/admin.css`
- `app/data/portfolio.json` (seed data)
- `app/static/img/uploads/` and `app/static/img/uploads/thumbs/` (runtime upload locations)

### Files Edited
- `app/__init__.py` (register admin blueprint)
- `app/config.py` (admin + upload config)
- `app/blueprints/public/routes.py` (load portfolio items)
- `app/templates/sections/_portfolio.html` (render from data)
- `app/templates/index.html` (lightbox description mapping)
- `app/static/css/pages/portfolio.css` (empty-state)
- `app/templates/admin/portfolio_list.html` (delete confirmation)
- `app/templates/admin/portfolio_form.html` (uploads + preview)
- `.gitignore` (track admin templates)
- `README.md`

## Project Structure
- `app/__init__.py` – Flask app factory and blueprint registration
- `app/blueprints/public` – Page routes (home, blog, game, resume)
- `app/blueprints/api` – API routes (contact, leaderboard)
- `app/blueprints/admin` – Admin auth + portfolio CRUD
- `app/portfolio/` – Portfolio store and helpers
- `app/templates/` – Jinja templates for pages/layout
- `app/static/` – Static assets (ensure `files/resume.pdf` exists)
- `app/data/portfolio.json` – Portfolio content store
- `ear_data/` – storage for the ear demo (dataset/audio, dataset/frames, pretrained_models, indexed_db.pt cache, uploads). Git-ignored by default; point `EAR_BASE_DIR` to move it elsewhere.

## Development Notes
- The contact route requires working SMTP credentials; without them it will 500.
- Adjust `MAIL_*` variables in `.env` or your shell to match your mail provider. The app loads `.env` explicitly from the project root, and `Config` will inject missing keys from `.env` into `os.environ` as a fallback (helps when supervisor/gunicorn starts with a different cwd).
- For production, set `MAIL_*` in your process manager (e.g., `environment=` in supervisor) if you prefer not to rely on `.env` file loading.
- Use `poetry run` before commands to ensure the virtualenv is active.
- The `/ear` demo reads from `ear_data/` by default (dataset, pretrained model, cache). Install the heavy deps manually (`torch`, `torchvision`, `torchaudio`, `Pillow`) and ensure the process user can read/write that folder. Override the location with `EAR_BASE_DIR=/absolute/path/to/ear_data` in your supervisor config if needed.

## Future Directions
- Replace the JSON portfolio store with a database (SQLite/Postgres) and migrations.
- Add image upload + storage management with validation and thumbnails.
- Expand admin roles/permissions (viewer/editor/publisher) and audit logging.
- Add draft/publish scheduling and content preview.
- Add WYSIWYG editor for descriptions while preserving safe HTML.
- Add tagging, search, and filtering for portfolio items.
