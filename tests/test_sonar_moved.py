import unittest
from unittest import mock

import requests

from app import create_app
from app.blueprints import sonar_share


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"sources": ["story"], "periods": [
            {"days": days, "since": "2026-10-01", "totals": {"views": 4, "app": 1, "appstore": 1, "ctr": 0.5},
             "rows": [{"kind": "review", "source": "story", "views": 4, "app": 1, "appstore": 1, "ctr": 0.5}]}
            for days in (7, 30)
        ]}


class SonarMovedTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-only", SONAR_STATS_TOKEN="secret")
        self.client = self.app.test_client()

    def test_old_links_redirect_for_good_and_keep_their_query(self):
        cases = {
            "/sonar": "https://sonar.show/",
            "/sonar/": "https://sonar.show/",
            "/sonar/support": "https://sonar.show/support",
            "/sonar/r/abc?s=story": "https://sonar.show/r/abc?s=story",
            "/sonar/u/maya/recap/2026": "https://sonar.show/u/maya/recap/2026",
            "/sonar/og/p/1.png": "https://sonar.show/og/p/1.png",
            "/sonar/badge/p/1.svg?theme=light": "https://sonar.show/badge/p/1.svg?theme=light",
        }
        for old, new in cases.items():
            response = self.client.get(old)
            self.assertEqual(response.status_code, 301, old)
            self.assertEqual(response.headers["Location"], new, old)

    def test_universal_links_file_stays_here_with_the_old_paths(self):
        for path in ("/.well-known/apple-app-site-association", "/apple-app-site-association"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "application/json")
            details = response.json["applinks"]["details"][0]
            self.assertEqual(details["appIDs"], ["9A9HR6WT4K.com.jeremyzay.Sonar"])
            self.assertIn({"/": "/sonar/r/*"}, details["components"])

    def test_stats_page_needs_the_admin(self):
        response = self.client.get("/admin/sonar")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

    def _admin_get(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
        return self.client.get("/admin/sonar")

    def test_stats_page_reads_the_sonar_site_with_the_token(self):
        with mock.patch.object(sonar_share.requests, "get", return_value=FakeResponse()) as get:
            response = self._admin_get()
        self.assertEqual(get.call_args.args[0], "http://127.0.0.1:8001/internal/stats")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer secret")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("Last 7 days", html)
        self.assertIn('<td data-label="Click-through">50.0%</td>', html)

    def test_stats_page_survives_the_sonar_site_being_down(self):
        with mock.patch.object(sonar_share.requests, "get", side_effect=requests.ConnectionError("down")):
            response = self._admin_get()
        self.assertEqual(response.status_code, 200)
        self.assertIn("couldn't be read", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
