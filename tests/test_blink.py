import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from app import create_app


class BlinkPagesTests(unittest.TestCase):
    """App Store Connect links to /blink/privacy and /blink/support, so they must keep answering."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-only")
        self.client = self.app.test_client()

    def test_pages_render_with_their_tabs(self):
        for path, heading in [
            ("/blink", "Blink"),
            ("/blink/support", "Blink support"),
            ("/blink/privacy", "Blink privacy policy"),
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            html = response.get_data(as_text=True)
            self.assertIn(f">{heading}</h1>", html, path)
            self.assertIn('aria-label="Blink pages"', html, path)
            self.assertIn('href="/blink/privacy"', html, path)

    def test_trailing_slashes_work(self):
        for path in ("/blink/", "/blink/support/", "/blink/privacy/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_blink_links_land_on_a_noindex_page(self):
        response = self.client.get("/blink/v?id=ABC")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Robots-Tag"), "noindex")
        self.assertIn("Open this Blink in Messages", response.get_data(as_text=True))

    def test_privacy_policy_covers_what_review_checks(self):
        html = self.client.get("/blink/privacy").get_data(as_text=True)
        for phrase in ("encrypt", "CloudKit", "deleted", "report", "camera", "contact page"):
            self.assertIn(phrase.lower(), html.lower(), phrase)



class BlinkAppClipTests(unittest.TestCase):
    """What the App Clip relies on: the association file, the banner, and deleting a viewed photo."""

    SNAP = "0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.key = os.path.join(self.tmp, "key.pem")
        subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", self.key], check=True)
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-only", BLINK_CK_KEY_ID="kid", BLINK_CK_KEY_PATH=self.key,
                               BLINK_REPORTS_DIR=os.path.join(self.tmp, "reports"), BLINK_APP_STORE_ID=None)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_association_file_lists_blink_links_and_clip(self):
        data = self.client.get("/.well-known/apple-app-site-association").get_json()
        details = {tuple(d["appIDs"]): d["components"] for d in data["applinks"]["details"]}
        self.assertEqual(details[("9A9HR6WT4K.com.jeremyzay.blink",)], [{"/": "/blink/v*"}])
        self.assertIn(("9A9HR6WT4K.com.jeremyzay.Sonar",), details)
        self.assertEqual(data["appclips"]["apps"], ["9A9HR6WT4K.com.jeremyzay.blink.Clip"])

    def test_clip_banner_only_once_the_app_id_is_set(self):
        self.assertNotIn("apple-itunes-app", self.client.get("/blink/v?id=x").get_data(as_text=True))
        self.app.config["BLINK_APP_STORE_ID"] = "123456"
        html = self.client.get("/blink/v?id=x").get_data(as_text=True)
        self.assertIn("app-id=123456, app-clip-bundle-id=com.jeremyzay.blink.Clip", html)

    def test_viewed_deletes_with_a_valid_signature(self):
        sent = {}

        def fake_post(url, data, headers, timeout):
            sent.update(url=url, data=data, headers=headers)
            response = mock.Mock(status_code=200)
            response.json.return_value = {"records": [{"recordName": self.SNAP}]}
            return response

        with mock.patch("app.blueprints.blink.cloudkit.requests.post", fake_post):
            response = self.client.post("/blink/api/viewed", json={"id": self.SNAP})
        self.assertEqual(response.status_code, 204)
        self.assertTrue(sent["url"].endswith("/iCloud.com.jeremyzay.blink/production/public/records/modify"))
        self.assertEqual(json.loads(sent["data"])["operations"][0], {"operationType": "forceDelete", "record": {"recordName": self.SNAP}})
        # The signature must verify against the key's public half, over date:sha256(body):subpath.
        h = sent["headers"]
        subpath = sent["url"].split("apple-cloudkit.com")[1]
        digest = base64.b64encode(hashlib.sha256(sent["data"]).digest()).decode()
        message = f"{h['X-Apple-CloudKit-Request-ISO8601Date']}:{digest}:{subpath}".encode()
        pub, sig = os.path.join(self.tmp, "pub.pem"), os.path.join(self.tmp, "sig.der")
        subprocess.run(["openssl", "ec", "-in", self.key, "-pubout", "-out", pub], check=True, capture_output=True)
        with open(sig, "wb") as f:
            f.write(base64.b64decode(h["X-Apple-CloudKit-Request-SignatureV1"]))
        check = subprocess.run(["openssl", "dgst", "-sha256", "-verify", pub, "-signature", sig], input=message, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertEqual(h["X-Apple-CloudKit-Request-KeyID"], "kid")

    def test_snap_returns_the_ciphertext_or_gone(self):
        def fake_post(url, data, headers, timeout):
            response = mock.Mock(status_code=200)
            response.raise_for_status = lambda: None
            if json.loads(data)["records"][0]["recordName"] == self.SNAP:
                response.json.return_value = {"records": [{"recordName": self.SNAP, "created": {"timestamp": int(time.time() * 1000)},
                                                           "fields": {"payload": {"value": {"downloadURL": "https://cvws.example/${f}"}}}}]}
            else:
                response.json.return_value = {"records": [{"serverErrorCode": "NOT_FOUND"}]}
            return response

        def fake_get(url, timeout):
            self.assertEqual(url, "https://cvws.example/payload")
            return mock.Mock(content=b"sealed-bytes", raise_for_status=lambda: None)

        with mock.patch("app.blueprints.blink.cloudkit.requests.post", fake_post), \
             mock.patch("app.blueprints.blink.cloudkit.requests.get", fake_get):
            ok = self.client.get(f"/blink/api/snap/{self.SNAP}")
            gone = self.client.get("/blink/api/snap/00000000-0000-0000-0000-000000000000")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data, b"sealed-bytes")
        self.assertEqual(ok.headers["Cache-Control"], "no-store")
        self.assertEqual(gone.status_code, 410)
        self.assertEqual(self.client.get("/blink/api/snap/nope").status_code, 400)

    def test_viewed_rejects_bad_ids_and_reports_missing_key(self):
        self.assertEqual(self.client.post("/blink/api/viewed", json={"id": "../etc"}).status_code, 400)
        self.app.config["BLINK_CK_KEY_ID"] = None
        self.assertEqual(self.client.post("/blink/api/viewed", json={"id": self.SNAP}).status_code, 503)

    def test_report_is_saved_with_the_photo(self):
        photo = base64.b64encode(b"\xff\xd8jpeg").decode()
        response = self.client.post("/blink/api/report", json={"id": self.SNAP, "reason": "spam", "photo": photo})
        self.assertEqual(response.status_code, 204)
        [folder] = os.listdir(os.path.join(self.tmp, "reports"))
        with open(os.path.join(self.tmp, "reports", folder, "report.json")) as f:
            self.assertEqual(json.load(f)["reason"], "spam")
        self.assertEqual(self.client.post("/blink/api/report", json={"id": self.SNAP, "reason": "nope"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
