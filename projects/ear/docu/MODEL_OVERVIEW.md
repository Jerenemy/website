# Project Manual: Architecture, Configuration & Operations
**Project:** Personal Website + Ear Microservice (Audio-Visual Retrieval)  
**Date:** December 16, 2025

---

## 1. Architecture Overview

To resolve memory constraints (OOM errors) and dependency conflicts on the VPS, the monolithic application was decoupled into two separate services running behind an Nginx reverse proxy.

### A. Main Website (Port 8000)
* **Role:** Portfolio, Blog, Static Pages.
* **Tech:** Flask (Standard).
* **Status:** Lightweight, always online.

### B. Ear Microservice (Port 5001)
* **Role:** PyTorch Audio-Visual Inference.
* **Tech:** Flask + PyTorch (CPU) + SoundFile + FFmpeg.
* **Status:** Heavy process. Isolated so crashes do not take down the main site.
* **Optimization:**
    * **Workers:** 1 (Reduces RAM usage).
    * **Preload:** Loads model before forking (Shared memory).
    * **Threads:** Restricted to 1 (Prevents CPU contention).
    * **Audio Backend:** Switched from `torchaudio` default to `soundfile` + system `ffmpeg` to handle browser uploads (`.webm`) and avoid `torchcodec` crashes.

---

## 2. Directory Structure

The project was reorganized into a monorepo-style structure to keep the root clean and isolate the ML project data.

```text
/home/jzay/personal_website/
├── pyproject.toml             # Shared dependencies for both apps
├── .venv/                     # Shared virtual environment
├── app/                       # MAIN WEBSITE CODE
│   ├── __init__.py            # Contains dev-mode redirect logic
│   ├── blueprints/
│   └── templates/
│
└── projects/                  # MINI-PROJECTS FOLDER
    └── ear/                   # EAR MICROSERVICE
        ├── service.py         # The Flask app (formerly ear_service.py)
        ├── indexed_db.pt      # Pre-computed dataset index
        ├── pretrained_models/ # Model weights
        │   └── best_audio_visual_clip.pt
        ├── ear_data/          # Dataset source
        │   ├── audio/         # .wav files
        │   └── frames/        # .jpg files
        └── uploads/           # Temporary storage for user queries
```

---

## 3. Configuration Files

### A. Nginx Configuration
**File:** `/etc/nginx/sites-enabled/personal_website`  
**Key Features:** Routes `/ear/` to port 5001, strips the URL prefix, and allows 50MB uploads.

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name jeremyzay.com [www.jeremyzay.com](https://www.jeremyzay.com);
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name jeremyzay.com [www.jeremyzay.com](https://www.jeremyzay.com);

    ssl_certificate /etc/letsencrypt/live/[jeremyzay.com/fullchain.pem](https://jeremyzay.com/fullchain.pem);
    ssl_certificate_key /etc/letsencrypt/live/[jeremyzay.com/privkey.pem](https://jeremyzay.com/privkey.pem);
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location /static/ {
        alias /home/jzay/personal_website/app/static/;
    }

    # 1. Main Website
    location / {
        proxy_pass http://localhost:8000;
        include /etc/nginx/proxy_params;
        proxy_redirect off;
    }

    # 2. Ear Microservice
    location = /ear {
        return 301 $scheme://$http_host/ear/;
    }

    location /ear/ {
        client_max_body_size 50M;       # Increased for audio files
        rewrite ^/ear/(.*) /$1 break;   # Strip /ear/ prefix
        proxy_pass [http://127.0.0.1:5001](http://127.0.0.1:5001);
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 120s;        # Long timeout for ML inference
        proxy_connect_timeout 120s;
    }
}
```

### B. Supervisor Configuration
**File:** `/etc/supervisor/conf.d/ear_service.conf`  
**Key Features:** Dedicated process control for the ML service.

```ini
[program:ear_service]
directory=/home/jzay/personal_website/projects/ear
command=/home/jzay/personal_website/.venv/bin/gunicorn 'service:app' --bind 127.0.0.1:5001 --workers 1 --timeout 120 --preload
user=jzay
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/log/personal_website/ear_service.err.log
stdout_logfile=/var/log/personal_website/ear_service.out.log
```

*(Note: The main website has its own separate config file running on port 8000).*

---

## 4. Operational Guide

### A. Local Development (Laptop)
You must run two terminals to simulate the production environment.

**Terminal 1: Main Site**
```bash
poetry shell
flask run --port 5000 --debug
```
* **Behavior:** `app/__init__.py` detects debug mode and redirects `/ear/` requests to port 5001.

**Terminal 2: Ear Service**
```bash
poetry shell
cd projects/ear
python service.py
```
* **Behavior:** Runs the ML backend on port 5001.

### B. Production Management (VPS)
Do not use `flask run`. Use `supervisorctl` to manage background processes.

```bash
# Check Status
sudo supervisorctl status

# Restart Main Website (HTML/CSS changes)
sudo supervisorctl restart personal_website

# Restart Ear Service (ML/Python logic changes)
sudo supervisorctl restart ear_service

# Restart Everything (Dependency updates)
sudo supervisorctl restart all
```

### C. Nginx Management
Required if you change routing rules or upload limits.

```bash
sudo nginx -t                # Check for syntax errors
sudo systemctl restart nginx # Apply changes
```

---

## 5. Maintenance & Troubleshooting

### A. Dependency Management
If `torchcodec` errors reappear or audio loading fails:

1.  **System Libraries:** Ensure the OS has the required drivers.
    ```bash
    sudo apt update && sudo apt install -y ffmpeg libsndfile1
    ```
2.  **Clean Environment:**
    ```bash
    # Force remove torchcodec (it conflicts with soundfile)
    poetry remove torchcodec
    poetry add "soundfile>=0.12.0"
    poetry install --sync
    ```

### B. Disk Space Cleanup
If the server disk fills up (check with `df -h`):

```bash
# Safe cleanup commands
rm -rf ~/.cache/pypoetry     # Clear poetry downloads
rm -rf ~/.cache/pip          # Clear pip downloads
sudo apt autoremove -y       # Remove unused system pkgs
sudo journalctl --vacuum-size=100M # Truncate logs
```

### C. Viewing Logs
When you hit a 500 Error, check these files immediately:

```bash
# Main Site Errors
tail -n 50 /var/log/personal_website/personal_website.err.log

# Ear Service Errors
tail -n 50 /var/log/personal_website/ear_service.err.log

# Nginx Errors (Gateway/Upload issues)
tail -n 50 /var/log/nginx/error.log
```