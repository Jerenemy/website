"""Just enough CloudKit Web Services for Blink: delete a viewed photo with a server-to-server key.

Requests are signed with ECDSA P-256 through the openssl command-line tool, so the site needs no
extra Python package. See Apple's "Composing Web Service Requests" (server-to-server keys)."""
import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone

import requests
from flask import current_app

API = "https://api.apple-cloudkit.com"


class NotConfigured(Exception):
    pass


def sign(message: bytes, key_path: str) -> str:
    """Base64 DER ECDSA-SHA256 signature of `message`, the form CloudKit expects."""
    result = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key_path],
                            input=message, capture_output=True, check=True, timeout=10)
    return base64.b64encode(result.stdout).decode()


def post(subpath: str, payload: dict) -> requests.Response:
    config = current_app.config
    key_id, key_path = config.get("BLINK_CK_KEY_ID"), config.get("BLINK_CK_KEY_PATH")
    if not key_id or not key_path:
        raise NotConfigured("BLINK_CK_KEY_ID and BLINK_CK_KEY_PATH are not set")
    body = json.dumps(payload, separators=(",", ":")).encode()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
    headers = {
        "Content-Type": "application/json",
        "X-Apple-CloudKit-Request-KeyID": key_id,
        "X-Apple-CloudKit-Request-ISO8601Date": date,
        "X-Apple-CloudKit-Request-SignatureV1": sign(f"{date}:{digest}:{subpath}".encode(), key_path),
    }
    return requests.post(API + subpath, data=body, headers=headers, timeout=15)


LIFETIME_MS = 7 * 24 * 60 * 60 * 1000


class Gone(Exception):
    pass


def fetch_snap(record_name: str) -> bytes:
    """The encrypted payload of one Snap. The key is only in the Blink's link, never sent here,
    so this is ciphertext. Raises Gone if it was deleted or has expired."""
    config = current_app.config
    subpath = f"/database/1/{config['BLINK_CK_CONTAINER']}/{config['BLINK_CK_ENV']}/public/records/lookup"
    response = post(subpath, {"records": [{"recordName": record_name}], "desiredKeys": ["payload"]})
    response.raise_for_status()
    [record] = response.json().get("records", [{}])[:1] or [{}]
    if record.get("serverErrorCode") or "fields" not in record:
        raise Gone()
    created = record.get("created", {}).get("timestamp", 0)
    if created and datetime.now(timezone.utc).timestamp() * 1000 - created > LIFETIME_MS:
        raise Gone()
    url = record["fields"]["payload"]["value"]["downloadURL"].replace("${f}", "payload")
    asset = requests.get(url, timeout=30)
    asset.raise_for_status()
    return asset.content


def delete_snap(record_name: str) -> bool:
    """Deletes one Snap record from the public database. True if it's gone (or already was)."""
    config = current_app.config
    subpath = f"/database/1/{config['BLINK_CK_CONTAINER']}/{config['BLINK_CK_ENV']}/public/records/modify"
    response = post(subpath, {"operations": [{"operationType": "forceDelete", "record": {"recordName": record_name}}]})
    if response.status_code != 200:
        current_app.logger.error("Blink delete failed: %s %s", response.status_code, response.text[:300])
        return False
    records = response.json().get("records", [])
    return all(r.get("serverErrorCode") in (None, "NOT_FOUND") for r in records)
