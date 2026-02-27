# DeltaLab Website Setup (Attack Target Network)

Target URL:

- `https://jeremyzay.com/deltalab/`

This is now set up in repo to run like EAR: separate process + nginx reverse proxy.

## What Is Already Updated In This Repo

1. `projects/attack_target_network/week_3_attack_target_graph_dash.py`
   - Supports subpath hosting via `DELTA_BASE_PATH` (required for Dash behind `/deltalab/`).
   - Accepts input files from either:
     - `outputs/week3/...` + `outputs/week1/...`
     - or `data_inputs/...` fallback.
2. `pyproject.toml` + `poetry.lock`
   - Includes `dash`, `gunicorn`, `pandas`, `plotly`, `networkx`.
3. Deploy snippets added:
   - `projects/attack_target_network/deploy/supervisor_attack_target_network.conf`
   - `projects/attack_target_network/deploy/nginx_deltalab_location.conf`

## Exact Server Steps

Run these on the VPS.

### 1. Pull and install deps

```bash
cd /home/jzay/personal_website
git pull
poetry install --no-root
```

### 2. Supervisor config

Copy the versioned config from repo:

```bash
sudo cp /home/jzay/personal_website/projects/attack_target_network/deploy/supervisor_attack_target_network.conf \
  /etc/supervisor/conf.d/attack_target_network.conf
```

If your CSV files are in a non-default directory, add `DELTA_DATA_ROOT` in the supervisor file:

```ini
environment=DELTA_BASE_PATH="/deltalab/",DELTA_DATA_ROOT="/absolute/path/to/your/csv/root"
```

`DELTA_DATA_ROOT` can point either to:

1. a directory containing `outputs/week3/...` and `outputs/week1/...`, or
2. a directory containing the files directly (for example `attack_target_edges_v1_1.csv`, etc.).

Load and start:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start attack_target_network
sudo supervisorctl status attack_target_network
```

This is the command you expected, and it will work once config is in place:

```bash
sudo supervisorctl start attack_target_network
```

### 3. Nginx config for `/deltalab/` (exact change)

Open your site config:

```bash
sudo vim /etc/nginx/sites-enabled/personal_website
```

Your current file already has the `/ear/` block.  
Add the DeltaLab block directly **after** the `/ear/` block and **before** the final `}` of the HTTPS `server` block.

Paste this:

```nginx
# --- 3. DeltaLab Dash Service (Port 5002) ---

# Force trailing slash (jeremyzay.com/deltalab -> jeremyzay.com/deltalab/)
location = /deltalab {
    return 301 $scheme://$http_host/deltalab/;
}

location /deltalab/ {
    proxy_pass http://127.0.0.1:5002;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_read_timeout 120s;
    proxy_connect_timeout 120s;
}
```

Important:

1. Do **not** add `rewrite ^/deltalab/(.*) /$1 break;` for DeltaLab.
2. Keep your `/ear/` block exactly as-is.
3. Add DeltaLab only inside the HTTPS `server { ... }` block (port `443`), not the HTTP redirect block (port `80`).

Or copy from:

- `projects/attack_target_network/deploy/nginx_deltalab_location.conf`

Then save and run:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo supervisorctl restart attack_target_network
```

## Verify It Is Live

```bash
sudo supervisorctl status attack_target_network
tail -n 80 /var/log/personal_website/attack_target_network.err.log
tail -n 80 /var/log/personal_website/attack_target_network.out.log
curl -I https://jeremyzay.com/deltalab/
```

Then open `https://jeremyzay.com/deltalab/` in browser and confirm callbacks/filters work.

## Fix For The Exact Error You Posted (`FileNotFoundError`)

If logs show `None of the candidate input paths exist`, the Dash service cannot find the 4 required CSVs.

Run:

```bash
cd /home/jzay/personal_website/projects/attack_target_network
ls -lh data_inputs/attack_target_edges_v1_1.csv \
       data_inputs/attack_target_nodes_v1_1.csv \
       data_inputs/entity_mentions_week3_cleaned_v1_1.csv.gz \
       data_inputs/harmonized_sample_week1.csv.gz
```

If any are missing, place/copy them into `data_inputs/` (or set `DELTA_DATA_ROOT` to where they already exist), then restart:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart attack_target_network
sudo supervisorctl status attack_target_network
tail -n 80 /var/log/personal_website/attack_target_network.err.log
```

## Notes About Existing Flask `/deltalab` Route

Your Flask app still has a legacy static `/deltalab` route. That is fine. Once nginx routes `/deltalab/` to port `5002`, nginx will serve the Dash app and effectively replace the current page.
