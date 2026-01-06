# Personal Website
A small Flask app for my personal site, serving static pages and a contact API that emails me via Flask-Mail.

## Features
- Home/portfolio/blog/game pages rendered with Jinja templates
- Contact endpoint posts to `/api/contact` and sends email via SMTP
- Resume served from `/resume` (backed by `app/static/files/`; filename stored in site settings)
- Simple stub leaderboard at `/api/leaderboard`
- Audio-visual retrieval demo mounted at `/ear` (uses data in `ear_data/`)
- Password-protected admin area to add/edit/delete portfolio items (JSON-backed) with image uploads, preview, and delete confirmation
- Admin site settings to update the home description/background, resume PDF, and theme colors

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
   # Optional: site settings storage + theme overrides
   # SITE_SETTINGS_PATH=/absolute/path/to/site_settings.json
   # SITE_FILES_DIR=/absolute/path/to/app/static/files
   # SITE_THEME_CSS_PATH=/absolute/path/to/app/static/css/theme.css
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
- Admin site settings: `http://127.0.0.1:5000/admin/settings`

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

## Site Settings Admin
- Settings live in `app/data/site_settings.json` (configurable via `SITE_SETTINGS_PATH`) and are created on first read.
- Manage settings at `/admin/settings` (requires admin login).
- Home description supports minimal HTML (rendered with `| safe`).
- Home background can be uploaded or set as a path relative to `/static`.
- Resume uploads are stored in `app/static/files/` (override with `SITE_FILES_DIR`); `/resume` serves the current filename with a fallback to `resume.pdf`.
- Theme colors are validated hex values and written to `app/static/css/theme.css` (override with `SITE_THEME_CSS_PATH`), which loads after `base.css`.

## Admin Integration
- The admin UI is a standalone blueprint (`/admin`) that uses the same portfolio + site settings stores as the public site.
- The public blueprint depends on the portfolio + site settings stores only; it does not depend on the admin blueprint.
- The API blueprint is independent of the admin system.
- Sessions and CSRF protection rely on `SECRET_KEY`; set it in production.

### Files Added
- `app/blueprints/admin/` (routes + blueprint registration)
- `app/portfolio/` (JSON store + helpers)
- `app/site_settings/__init__.py` (site settings store accessor)
- `app/site_settings/store.py` (JSON-backed site settings with defaults + timestamps)
- `app/templates/admin/` (login, list, form, flash partial)
- `app/templates/admin/site_settings.html` (admin settings form)
- `app/static/css/pages/admin.css`
- `app/static/css/theme.css` (theme variable overrides; updated by admin)
- `app/data/portfolio.json` (seed data)
- `app/static/img/uploads/` and `app/static/img/uploads/thumbs/` (runtime upload locations)

### Files Edited
- `app/__init__.py` (register admin blueprint)
- `app/config.py` (add site settings paths + theme CSS path)
- `app/blueprints/admin/routes.py` (add `/admin/settings`, PDF upload validation, theme CSS writer)
- `app/blueprints/public/routes.py` (load site settings for home; serve resume from settings with fallback)
- `app/templates/sections/_portfolio.html` (render from data)
- `app/templates/sections/_home.html` (use settings for background + description)
- `app/templates/index.html` (lightbox description mapping)
- `app/templates/base.html` (load `theme.css` after `base.css`)
- `app/static/css/pages/portfolio.css` (empty-state)
- `app/templates/admin/portfolio_list.html` (add link to site settings)
- `app/templates/admin/portfolio_form.html` (add link to site settings)
- `.gitignore` (track admin templates)
- `README.md`

## Project Structure
- `app/__init__.py` – Flask app factory and blueprint registration
- `app/blueprints/public` – Page routes (home, blog, game, resume)
- `app/blueprints/api` – API routes (contact, leaderboard)
- `app/blueprints/admin` – Admin auth + portfolio CRUD + site settings
- `app/portfolio/` – Portfolio store and helpers
- `app/site_settings/` – Site settings store and helpers
- `app/templates/` – Jinja templates for pages/layout
- `app/static/` – Static assets (ensure `files/resume.pdf` exists as a fallback)
- `app/static/css/theme.css` – Theme override variables (generated by admin)
- `app/data/portfolio.json` – Portfolio content store
- `app/data/site_settings.json` – Site settings store (auto-created)
- `ear_data/` – storage for the ear demo (dataset/audio, dataset/frames, pretrained_models, indexed_db.pt cache, uploads). Git-ignored by default; point `EAR_BASE_DIR` to move it elsewhere.

## Development Notes
- The contact route requires working SMTP credentials; without them it will 500.
- Adjust `MAIL_*` variables in `.env` or your shell to match your mail provider. The app loads `.env` explicitly from the project root, and `Config` will inject missing keys from `.env` into `os.environ` as a fallback (helps when supervisor/gunicorn starts with a different cwd).
- For production, set `MAIL_*` in your process manager (e.g., `environment=` in supervisor) if you prefer not to rely on `.env` file loading.
- Use `poetry run` before commands to ensure the virtualenv is active.
- The site settings JSON and `theme.css` are created/updated at runtime when you save settings in `/admin/settings`.
- The `/ear` demo reads from `ear_data/` by default (dataset, pretrained model, cache). Install the heavy deps manually (`torch`, `torchvision`, `torchaudio`, `Pillow`) and ensure the process user can read/write that folder. Override the location with `EAR_BASE_DIR=/absolute/path/to/ear_data` in your supervisor config if needed.

## Future Directions
- Replace the JSON portfolio store with a database (SQLite/Postgres) and migrations.
- Add image upload + storage management with validation and thumbnails.
- Expand admin roles/permissions (viewer/editor/publisher) and audit logging.
- Add draft/publish scheduling and content preview.
- Add WYSIWYG editor for descriptions while preserving safe HTML.
- Add tagging, search, and filtering for portfolio items.
