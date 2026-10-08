# Personal Website
A small Flask app for my personal site, serving static pages and a contact API that emails me via Flask-Mail.


## Run the App
```bash
poetry run flask --app app:create_app run --debug
```
- The site will be available at `http://127.0.0.1:5000/`
- Contact POST endpoint: `http://127.0.0.1:5000/api/contact`
- Leaderboard GET endpoint: `http://127.0.0.1:5000/api/leaderboard`
- Admin login: `http://127.0.0.1:5000/admin`
- Admin site settings: `http://127.0.0.1:5000/admin/settings`

## If problem with env and need to reinstall: 
poetry install --no-root

## Features
- Dynamic, Apple-style mobile navigation menu with a zero-layout-shift sliding drawer animation and an intelligent breakpoint calculator
- Responsive sticky header with automatic background lightness detection to adapt its frosted glass contrast
- Home/portfolio/blog/game pages rendered with Jinja templates
- Blog posts auto-loaded from Markdown files in `app/blog_posts/`
- Contact endpoint posts to `/api/contact` and sends email via SMTP
- Resume served from `/resume` (backed by `app/static/files/`; filename stored in site settings)
- Simple stub leaderboard at `/api/leaderboard`
- Audio-visual retrieval demo mounted at `/ear` (uses data in `ear_data/`)
- Password-protected admin area to add/edit/delete portfolio items (JSON-backed) with image uploads, preview, and delete confirmation
- Admin site settings to update the home description/background, resume PDF, and theme colors

## Homepage (TRIBAR)

`/` renders `app/templates/home.html`: the published items of `app/data/portfolio.json` as a server-rendered list (the whole page without JavaScript or WebGL 2, or if the scene's files fail to load) plus the same data as JSON in `#site-data`, which the WebGL scene in `app/static/home/` reads. Each published item is one step of the monument, in `sort_order`; adding or reordering works in `/admin/portfolio` needs no code change. `/contact` is the contact form in the same style (it also works without JavaScript); old `/#contact` links land there. The scene is plain ES modules (`app/static/home/src/`, no build step, all preloaded by `home.html`); three.js is one minified file, `app/static/home/vendor/three-r186/three.module.min.js`, versioned by its folder. Link previews use `app/static/img/brand/tribar-preview.jpg` (1200 x 630, a frame of the homepage). The design notes and the proofs (`tools/check-geometry.mjs`, `tools/regress.sh`) live in `design/homepage-demo/`, whose `src`, `styles.css` and `vendor` are symlinks to the production files.

### Deploying the homepage

**On your Mac**, stage everything and read the list before committing:

```bash
cd ~/Desktop/coding_projects/websites/personal_website
git add -A
git status --short   # 49 A, 13 M, 4 D: only under app/, design/homepage-demo/, deploy/, tests/, plus README.md and .gitignore; nothing from .env, instance/ or __pycache__
```

Then commit and push (or merge into `main` and push that):

```bash
git commit -m 'feat: TRIBAR homepage' && git push -u origin homepage-redesign
```

**On the server**, as `jzay`. No new Python packages; `.env`, `instance/` and `site_settings.json` are untouched. Every block can be run again: the rollback point and the backups are taken on the first run only.

1. Check what the deploy will touch:

```bash
cd /home/jzay/personal_website
REF=origin/homepage-redesign                       # or origin/main once the branch is merged
git fetch origin
[ -e ~/pre-homepage.rev ] || git rev-parse HEAD > ~/pre-homepage.rev                          # for the rollback
[ -e ~/portfolio.pre-homepage.json ] || cp app/data/portfolio.json ~/portfolio.pre-homepage.json
git diff --name-only HEAD "$REF" | xargs -r git status --short --   # files the deploy changes that were edited here: must print nothing
```

A plain `git status` on the server also lists files the admin pages write, which this deploy does not touch and git carries across: ` M app/static/css/theme.css` (the theme colours) and `?? app/static/files/resume-….pdf` (the current résumé). They are expected; never `git checkout`, `stash` or `clean` them. If the check above lists `app/data/portfolio.json`, the works were edited in `/admin/portfolio` here: the copy just made keeps those edits; run `git checkout -- app/data/portfolio.json` and re-enter them in the admin after the deploy.

EAR (`/ear/`) ships unpublished, because its service is down (502). It comes back as a work once it answers (an admin edit: see "Editing works on the server" below):

```bash
sudo supervisorctl status ear_service
curl -s -o /dev/null -w '%{http_code}\n' https://jeremyzay.com/ear/   # 200: publish EAR in /admin/portfolio after the deploy
```

2. nginx first: gzip for CSS/JS/JSON/SVG, a year's cache for the versioned three.js, five minutes for the rest of `/static/`, and HTTP/2. The current app runs unchanged under it. The live file is the one in `sites-enabled` that serves jeremyzay.com (`projects/attack_target_network/docs` edits `/etc/nginx/sites-enabled/personal_website`); `readlink` follows it to `sites-available` if it is a link. It is replaced only if it is exactly the repository's current copy; otherwise the change is printed, to be made by hand.

```bash
grep -l 'server_name jeremyzay.com' /etc/nginx/sites-enabled/*         # must list exactly one file
CONF=$(readlink -f "$(grep -l 'server_name jeremyzay.com' /etc/nginx/sites-enabled/* | head -1)"); echo "$CONF"
[ -e ~/nginx-personal_website.conf.bak ] || sudo cp "$CONF" ~/nginx-personal_website.conf.bak   # outside sites-enabled (nginx loads every file there)
if git show HEAD:deploy/nginx/personal_website.conf | sudo diff -q - "$CONF" >/dev/null; then
  git show "$REF":deploy/nginx/personal_website.conf | sudo tee "$CONF" >/dev/null
  sudo nginx -t && sudo systemctl reload nginx || { sudo cp ~/nginx-personal_website.conf.bak "$CONF"; echo 'nginx -t failed: old config restored'; }
else
  echo "$CONF differs from the repository (Certbot or a hand edit): make this change to it by hand, then: sudo nginx -t && sudo systemctl reload nginx"
  git diff HEAD "$REF" -- deploy/nginx/personal_website.conf
fi
```

3. The app, in one go (the update removes the old homepage templates, so the restart follows at once):

```bash
git checkout "${REF#origin/}" && git merge --ff-only "$REF" && sudo supervisorctl restart personal_website
sudo supervisorctl status personal_website
```

Verify:

```bash
curl -s https://jeremyzay.com/ | grep -c 'data-index='                       # one per published work (9 while EAR is unpublished)
curl -s https://jeremyzay.com/ | grep -c 'id="site-data"'                     # 1
curl -s -o /dev/null -w '%{http_code}\n' https://jeremyzay.com/contact        # 200
curl -s -o /dev/null -w '%{http_version}\n' https://jeremyzay.com/            # 2
# every file the homepage loads is served by nginx (prints only the summary line)
for f in app/static/home/src/*.js app/static/home/*.css app/static/home/vendor/three-r186/three.module.min.js app/static/img/brand/tribar-preview.jpg; do
  printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "https://jeremyzay.com/${f#app/}")" "$f"; done | grep -v '^200 ' || echo 'all 200'
curl -s -o /dev/null -D - -H 'Accept-Encoding: gzip' https://jeremyzay.com/static/home/vendor/three-r186/three.module.min.js | grep -iE 'content-encoding|cache-control|vary'
#   content-encoding: gzip / cache-control: public, max-age=31536000, immutable / vary: Accept-Encoding
curl -s -o /dev/null -D - -H 'Accept-Encoding: gzip' https://jeremyzay.com/static/home/src/main.js | grep -iE 'content-encoding|cache-control'
#   content-encoding: gzip / cache-control: public, max-age=300
curl -s -o /dev/null -D - https://jeremyzay.com/ | grep -ci cache-control      # 0: pages are not cached
curl -s -o /dev/null -D - https://jeremyzay.com/wtt | grep -i cache-control    # exactly one line: no-store
```

Then in a browser: `/` (the monument settles, the rail on the right), `/?nogl=1` (the plain list, the links beside the name), `/#contact` (the contact page), `/contact` (send yourself a message).

Rollback (the nginx change serves the old code too; restore it only if nginx itself is the problem):

```bash
cd /home/jzay/personal_website
cp app/data/portfolio.json ~/portfolio.post-homepage.json   # edits made since the deploy, in the new format
git checkout -- app/data/portfolio.json
git checkout "$(cat ~/pre-homepage.rev)" && cp ~/portfolio.pre-homepage.json app/data/portfolio.json && sudo supervisorctl restart personal_website
# detached HEAD; `git checkout main` returns later. Only for nginx itself:
sudo cp ~/nginx-personal_website.conf.bak "$(readlink -f "$(grep -l 'server_name jeremyzay.com' /etc/nginx/sites-enabled/* | head -1)")" && sudo nginx -t && sudo systemctl reload nginx
```

### Editing works on the server

`app/data/portfolio.json` is tracked, so every save in `/admin/portfolio` on the server changes it, and the next deploy's check stops on it. To keep the server's works out of git, once the homepage is live:

```bash
cd /home/jzay/personal_website
cp app/data/portfolio.json instance/portfolio.json
echo 'PORTFOLIO_DATA_PATH=/home/jzay/personal_website/instance/portfolio.json' >> .env
sudo supervisorctl restart personal_website
```

From then on the admin writes `instance/portfolio.json` and the tracked file only seeds new checkouts: works changed in the repository no longer reach the live site (change them in the admin). To undo, and before any rollback to the old code, delete that line from `.env` and restart.

## Automatic deploys

`.github/workflows/deploy.yml` runs on every push to `main` (and by hand from the Actions tab). It SSHes into the server, fast-forwards `/home/jzay/personal_website` to `origin/main`, restarts `personal_website`, and restarts `ear_service` or `attack_target_network` only when their folder under `projects/` changed. A pull that would overwrite a file edited on the server (the admin pages' `theme.css`, `portfolio.json`) fails the run and leaves the server as it was. It never touches the Python environment: `pyproject.toml` and `poetry.lock` are untracked, so the server and the Mac each keep their own, and a new dependency is installed on the server by hand.

One-time setup:

1. On the server, as `jzay`, make a key for the workflow and authorize it:

```bash
ssh-keygen -t ed25519 -N '' -C github-deploy -f ~/.ssh/github_deploy && cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
```

2. Let `jzay` restart the programs without a password (`sudo visudo -f /etc/sudoers.d/github-deploy`):

```
jzay ALL=(root) NOPASSWD: /usr/bin/supervisorctl restart personal_website, /usr/bin/supervisorctl restart ear_service, /usr/bin/supervisorctl restart attack_target_network, /usr/bin/supervisorctl status
```

3. In GitHub, Settings → Secrets and variables → Actions, add `DEPLOY_HOST` (the server's address), `DEPLOY_USER` (`jzay`), `DEPLOY_SSH_KEY` (the contents of `~/.ssh/github_deploy`) and, if SSH is not on 22, `DEPLOY_PORT`.

## WTT Email Signup

- Public form: `https://jeremyzay.com/wtt` (also accepts `/wtt/`). Collects emails only; no email is sent.
- Private list: `/admin/wtt`; CSV download: `/admin/wtt/export.csv`. Both require the existing admin login. The portfolio admin links to the list.
- Printable QR assets: `app/static/files/wtt-qr.svg` (vector) and `app/static/files/wtt-qr.png` (raster). They encode exactly `https://jeremyzay.com/wtt`, with a white quiet zone; preserve that border when printing.
- Stores normalized, case-insensitive unique email addresses and UTC signup times. Duplicate signups receive the same success message. CSV cells beginning with spreadsheet formula characters are prefixed with an apostrophe for safe spreadsheet use.

### Storage and deployment

SQLite uses Python's standard library; no new runtime package or database service is needed. The default is the Git-ignored `instance/wtt.sqlite3`, outside `/static`. For production, put it in a persistent private directory owned by the supervisor process user (`jzay`) so replacing a checkout does not remove signups:

```bash
install -d -m 700 /home/jzay/personal_website_data
```

Set these in the server's `.env` (keep existing admin credentials):

```dotenv
WTT_DATABASE_PATH=/home/jzay/personal_website_data/wtt.sqlite3
SECRET_KEY=your-existing-stable-secret-key
```

Use a fixed `SECRET_KEY` shared by all three Gunicorn workers; a per-process random fallback makes form CSRF tokens unreliable. Keep the database path outside static directories and preserve the data directory across deployments. Initialize as `jzay` from `/home/jzay/personal_website`:

```bash
.venv/bin/flask --app app:create_app init-wtt-db
sudo supervisorctl restart personal_website
sudo supervisorctl status personal_website
```

Initialization is idempotent and also happens on first database access. Existing tables and signups are preserved. No Nginx or Supervisor configuration change is required. If moving an existing database, stop the app, back it up to the new location, update the path, and restart.

### Backup and verification

Use SQLite's backup API for a consistent backup while the app is running. Run from the project directory with the same environment as the app; choose a private, persistent destination, and copy backups off the server as part of your normal backup routine:

```bash
.venv/bin/python - <<'PY'
import sqlite3
from contextlib import closing
from app import create_app
app = create_app()
with closing(sqlite3.connect(app.config['WTT_DATABASE_PATH'])) as source:
    with closing(sqlite3.connect('/home/jzay/personal_website_data/wtt-backup.sqlite3')) as backup:
        source.backup(backup)
PY
```

Restore with the app stopped, placing the backup at `WTT_DATABASE_PATH` with ownership and permissions allowing `jzay` to write to both the file and its directory, then restart the process. Neither emails nor backups belong in Git or static files.

Run `.venv/bin/python -m unittest discover -s tests -v` for signup, validation, concurrent duplicate, persistence, storage failure, CSRF, spam-trap, and admin/export checks. After deploying, scan the QR code on a phone, submit a test signup, verify it under `/admin/wtt`, and download the CSV. Check `/var/log/personal_website/personal_website.err.log` for storage errors if a signup fails.

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
   # BLOG_POSTS_DIR=/absolute/path/to/app/blog_posts
   # Optional: upload limits/paths
   # MAX_UPLOAD_MB=6
   # UPLOADS_DIR=/absolute/path/to/app/static/img/uploads
   # UPLOADS_THUMBS_DIR=/absolute/path/to/app/static/img/uploads/thumbs
   ```
   Generate a password hash:
   ```bash
   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
   ```

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
  - `title` (at most 24 characters: one line on a phone), `kind` (research, engineering, product or play), `line` (one short plain-text sentence) and `href` (a site path like `/blog/zaybot` or an `https://` URL): what the homepage shows; all required
  - `sort_order` (its place on the homepage loop), `is_published`
  - `short_desc` (card text), `long_desc` (lightbox text), `image_full`, `image_thumb` (paths relative to `/static`), `image_alt`: optional, kept for the record (no page shows them now); alt text is required only with an image
- New items get a readable id from the title (it appears in the homepage URL, e.g. `/#curve-explorer`).
- HTML is allowed in `short_desc` and `long_desc` (e.g., links). Keep markup minimal.

## Site Settings Admin
- Settings live in `app/data/site_settings.json` (configurable via `SITE_SETTINGS_PATH`) and are created on first read.
- Manage settings at `/admin/settings` (requires admin login).
- Home description supports minimal HTML. The homepage no longer shows it; with the HTML stripped it is the site's `<meta name="description">` (search results and link previews).
- Home background can be uploaded or set as a path relative to `/static` (unused by the TRIBAR homepage).
- Resume uploads are stored in `app/static/files/` (override with `SITE_FILES_DIR`); `/resume` serves the current filename with a fallback to `resume.pdf`.
- Theme colors are validated hex values and written to `app/static/css/theme.css` (override with `SITE_THEME_CSS_PATH`), which loads after `base.css`.

## Admin Integration
- The admin UI is a standalone blueprint (`/admin`) that uses the same portfolio + site settings stores as the public site.
- The public blueprint depends on the portfolio + site settings stores only; it does not depend on the admin blueprint.
- The API blueprint is independent of the admin system.
- Sessions and CSRF protection rely on `SECRET_KEY`; set it in production.

## Blog Posts
- Add a `.md` file to `app/blog_posts/` and it appears automatically at `/blog`.
- URL slugs are generated from filenames (for example, `my-first-post.md` -> `/blog/my-first-post`).
- Optional front matter is supported:
  ```md
  ---
  title: My Post Title
  date: 2026-02-23
  summary: One-line summary used on the blog index.
  ---
  ```

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
- `app/templates/` – Jinja templates for pages/layout (`home.html` and `contact.html` stand alone; the other pages extend `base.html`)
- `app/static/home/` – the homepage scene: `src/` (ES modules), `styles.css`, `vendor/three-r186/` (its colours, type and curve come from `app/static/site/tokens.css`)
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

- Fix colors of contact fields to be consistent with the rest of the defaults.

## Clash Royale friendly battle table

`/will-sucks` displays the seeded Jer/Will/Win/Leo head-to-head wins. Anyone can add a player tag or sync; forms use CSRF protection, a 60-second shared sync cooldown, and five add attempts per client IP per ten minutes. Diagonals show a dash. Only completed `friendly` 1v1 matches between registered players count; draws and all other modes are excluded. Initial logs are baselined so existing scores are not counted again.

### Configuration and activation

Set these in the server's private `.env`:

```dotenv
CLASH_ROYALE_API_KEY=your-developer-key
CLASH_ROYALE_DATABASE_PATH=/home/jzay/personal_website_data/clash.sqlite3
# Optional; defaults to the official endpoint:
CLASH_ROYALE_API_BASE_URL=https://api.clashroyale.com/v1
```

`CLASH_ROYALE_API_TOKEN` is also supported and takes precedence over `CLASH_ROYALE_API_KEY`. Retain a stable `SECRET_KEY` across Gunicorn workers. The database defaults locally to ignored `instance/clash.sqlite3`; keep production data outside the checkout, owned by `jzay`, and outside public/static directories.

Create a developer key at [Clash Royale Developers](https://developer.clashroyale.com/) allowing the server's public outgoing IP. HTTP 403 can indicate an unapproved IP. For servers without a stable IP, follow the [RoyaleAPI proxy instructions](https://docs.royaleapi.com/proxy.html), whitelist their documented IP, and set the base URL to `https://proxy.royaleapi.dev/v1`. Never expose the key in browser code or commit `.env`.

From `/home/jzay/personal_website`, as `jzay`:

```bash
install -d -m 700 /home/jzay/personal_website_data
.venv/bin/flask --app app:create_app init-clash-db
.venv/bin/flask --app app:create_app verify-clash-friendly
.venv/bin/flask --app app:create_app sync-clash
```

Verification must find a live friendly 1v1 match with valid tags, battle time, crowns, and mode data in one registered player's recent log. Play a friendly and retry if none is available. Score updates remain disabled until verification succeeds; the first successful verified sync baselines each account. Accounts with failed initial fetches begin counting only after their first successful baseline. A verified account added later starts at registration with zero wins. Seed labels stay fixed; added accounts use their API name.

Restart the website after changing environment settings. The existing Nginx configuration now overwrites `X-Real-IP`; deploy it and reload Nginx so account-add limits distinguish users behind the loopback-bound Gunicorn server. Forwarded IPs are trusted only when requests originate on loopback.

### Daily scheduling

Install the supplied units on the production Linux server:

```bash
sudo cp deploy/systemd/clash-royale-sync.service deploy/systemd/clash-royale-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clash-royale-sync.timer
sudo systemctl start clash-royale-sync.service
sudo systemctl list-timers clash-royale-sync.timer
sudo journalctl -u clash-royale-sync.service
```

The timer runs at 4 a.m. `America/New_York`, follows daylight saving time, and catches up after downtime. It runs the same sync code as the button. The database lease prevents concurrent jobs across workers. API failures preserve previous logs and scores; successful accounts can still contribute results, and partial failures cause a nonzero CLI exit for monitoring.

Recent logs are finite. Daily syncing cannot guarantee every match is captured. The page always explains this and flags possible gaps when consecutive nonempty logs have no matches in common. Cached logs and globally deduplicated processed matches prevent double counting; they cannot reconstruct disappeared history.

### Backup and smoke test

Use SQLite's backup API, as in the WTT backup instructions, with source `CLASH_ROYALE_DATABASE_PATH` and a private destination such as `/home/jzay/personal_website_data/clash-backup.sqlite3`. Copy backups off-server. Stop both the timer and website before restoring; restore ownership, then restart both. Initialization preserves existing players and scores.

Run `.venv/bin/python -m unittest discover -s tests -v`. After deployment, verify the exact starting matrix, activate tracking and baseline, play a new friendly between two registered accounts, and click Sync Now. Only the winner's cell should increment. After the cooldown, repeat the sync and confirm it does not increment again. Check mobile horizontal scrolling, keyboard form access, duplicate-tag handling, scheduler status, and the journal for failures.
