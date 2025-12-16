# Audio-Visual Retrieval Project Refactoring Summary

## 1. Overview
The original monolithic Flask application was crashing due to **Out Of Memory (OOM)** errors on the VPS. The heavy PyTorch model (768MB+) was fighting for RAM with the personal website.

We resolved this by decoupling the AI component into a **standalone microservice** running on a separate port, optimized for low-memory environments.

---

## 2. Architecture Changes
* **Split Services:**
    * **Main Site (Port 8000):** Lightweight Flask app (Portfolio, Blog).
    * **Ear Service (Port 5001):** Heavy PyTorch microservice.
* **Traffic Routing:** Nginx now acts as a reverse proxy, routing requests to `/ear/` to the microservice while keeping the main site fast.
* **Memory Optimization:**
    * Reduced Gunicorn workers from 3 to **1**.
    * Enabled `--preload` to load the model before forking.
    * Limited PyTorch threads to **1** to prevent CPU contention.

---

## 3. Dependency & Environment Fixes
* **PyTorch CPU:** Forced `pyproject.toml` to use the `pytorch-cpu` source to avoid downloading massive NVIDIA GPU libraries (saving GBs of disk/RAM).
* **Removed `torchcodec`:** This library caused persistent "FFmpeg/DLL not found" errors.
* **Added `soundfile` + `ffmpeg`:** Switched audio backend to `soundfile` and installed system-level FFmpeg for robust audio conversion.
* **Package Cleanup:** Ran `poetry remove torchcodec` and `sudo apt install ffmpeg libsndfile1`.

---

## 4. Code & Logic Improvements

### `projects/ear/service.py`
* **Robust Audio Loading:** Replaced `torchaudio.load` with a custom pipeline:
    1.  Use `subprocess` to call system `ffmpeg` (converts `.webm`/browser audio to clean 16kHz WAV).
    2.  Read WAV using `soundfile`.
    3.  Convert to PyTorch tensor manually.
* **Routing Fixes:** Added dual decorators (`@app.route('/data/...')` and `@app.route('/ear/data/...')`) so the app works both locally and behind Nginx.
* **Frontend Fixes:** Updated the embedded JavaScript to handle file naming correctly (fixing the "Format not recognised" error on uploads).

### `app/__init__.py` (Main Site)
* **Dev Mode Redirect:** Added logic to redirect `/ear/` to `localhost:5001` when running locally (`debug=True`), mimicking Nginx's production behavior.

---

## 5. Infrastructure Configuration

### Nginx (`/etc/nginx/sites-enabled/personal_website`)
* Added `location /ear/` block.
* **Stripping Prefix:** Uses `rewrite ^/ear/(.*) /$1 break;` so the internal app sees clean paths.
* **Upload Limit:** Increased `client_max_body_size` to **50M** to allow audio file uploads.
* **Timeouts:** Increased `proxy_read_timeout` to **120s** for ML inference.

### Supervisor (`/etc/supervisor/conf.d/ear_service.conf`)
* Created a dedicated config for the microservice.
* Command: `gunicorn 'service:app' --bind 127.0.0.1:5001 --workers 1 --timeout 120 --preload`

---

## 6. Final Directory Structure
We moved the project from the root into a clean subdirectory structure:

```text
/home/jzay/personal_website/
├── pyproject.toml             # Shared dependencies
├── .venv/                     # Shared environment
├── app/                       # Main Website Code
│
└── projects/                  # NEW: Mini-projects folder
    └── ear/
        ├── service.py         # The Microservice
        ├── indexed_db.pt      # Pre-computed dataset index
        ├── pretrained_models/ # Model weights
        │   └── best_audio_visual_clip.pt
        ├── ear_data/          # Dataset
        │   ├── audio/         # .wav files
        │   └── frames/        # .jpg files
        └── uploads/           # Temp storage