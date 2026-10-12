import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

from app import create_app
from app.blueprints.sonar_share import attribution, data, og

LOG_ID = "d351c000-0000-4000-8003-000000000000"
SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1"
BOTS = (
    "facebookexternalhit/1.1 Facebot Twitterbot/1.0",  # iMessage link previews
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Twitterbot/1.0",
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "WhatsApp/2.23.20.0 A",
    "TelegramBot (like TwitterBot)",
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)",
    "LinkedInBot/1.0 (compatible; Mozilla/5.0)",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "curl/8.4.0",
    "",
)


class SonarAttributionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "instance", "sonar_stats.sqlite3")
        self.app.config.update(
            TESTING=True,
            SONAR_OG_CACHE_DIR=os.path.join(self.tmp, "og"),
            SONAR_STATS_DATABASE_PATH=self.db_path,
            SONAR_SUPABASE_URL=None,
            PODCASTINDEX_API_KEY=None,
        )
        self.client = self.app.test_client()
        data._cache.clear()
        og.clear_memory_cache()
        # Every page lookup comes back empty: the pages render their "missing" variants.
        patchers = [mock.patch.object(data.requests, "get", side_effect=AssertionError("network"))]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _views(self):
        if not os.path.exists(self.db_path):
            return []
        with sqlite3.connect(self.db_path) as connection:
            return connection.execute("SELECT kind, source, count FROM sonar_share_views ORDER BY kind, source").fetchall()

    def _clicks(self):
        if not os.path.exists(self.db_path):
            return []
        with sqlite3.connect(self.db_path) as connection:
            return connection.execute(
                "SELECT kind, source, target, count FROM sonar_share_clicks ORDER BY kind, source, target"
            ).fetchall()

    # --- Views ---------------------------------------------------------------------------

    def test_page_views_are_counted_by_kind_and_source(self):
        get = lambda path: self.client.get(path, headers={"User-Agent": SAFARI})  # noqa: E731
        self.assertEqual(get(f"/sonar/r/{LOG_ID}?s=story").status_code, 200)
        get(f"/sonar/r/{LOG_ID}?s=story")
        get(f"/sonar/r/{LOG_ID}")
        get("/sonar/e/1/2?s=REVIEW")
        get("/sonar/i/maya?s=invite")
        get(f"/sonar/r/{LOG_ID}?s=somewhere-else")
        self.assertEqual(self._views(), [
            ("episode", "review", 1),
            ("invite", "invite", 1),
            ("review", "story", 2),
            ("review", "unknown", 2),
        ])

    def test_link_previews_and_crawlers_are_not_counted(self):
        for ua in BOTS:
            response = self.client.get(f"/sonar/r/{LOG_ID}?s=story", headers={"User-Agent": ua})
            self.assertEqual(response.status_code, 200, ua)
            go = self.client.get(f"/sonar/go?to=appstore&k=review&s=story&u=/sonar/r/{LOG_ID}", headers={"User-Agent": ua})
            self.assertEqual(go.status_code, 302, ua)
        self.client.get(f"/sonar/r/{LOG_ID}", headers={"User-Agent": SAFARI, "Sec-Purpose": "prefetch"})
        self.client.head(f"/sonar/r/{LOG_ID}", headers={"User-Agent": SAFARI})
        self.assertEqual(self._views(), [])
        self.assertEqual(self._clicks(), [])

    def test_bot_detection(self):
        for ua in BOTS:
            self.assertTrue(attribution.is_bot(ua), ua)
        for ua in (SAFARI,
                   "Mozilla/5.0 (Linux; Android 13; CUBOT X30) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"):
            self.assertFalse(attribution.is_bot(ua), ua)

    def test_store_keeps_no_visitor_data(self):
        self.client.get(f"/sonar/r/{LOG_ID}?s=story", headers={"User-Agent": SAFARI, "X-Forwarded-For": "203.0.113.9"},
                        environ_base={"REMOTE_ADDR": "198.51.100.7"})
        self.client.get(f"/sonar/go?to=app&s=story&u=/sonar/r/{LOG_ID}", headers={"User-Agent": SAFARI})
        with sqlite3.connect(self.db_path) as connection:
            columns = {
                table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
                for table in ("sonar_share_views", "sonar_share_clicks")
            }
            dump = "\n".join(connection.iterdump())
        self.assertEqual(columns["sonar_share_views"], ["day", "kind", "source", "count"])
        self.assertEqual(columns["sonar_share_clicks"], ["day", "kind", "source", "target", "count"])
        for secret in ("203.0.113.9", "198.51.100.7", "iPhone", "Mozilla", LOG_ID):
            self.assertNotIn(secret, dump)
        # Pages and redirects set no cookies.
        response = self.client.get(f"/sonar/r/{LOG_ID}", headers={"User-Agent": SAFARI})
        self.assertNotIn("Set-Cookie", response.headers)

    def test_storage_failure_never_breaks_a_page(self):
        self.app.config.update(SONAR_STATS_DATABASE_PATH=os.path.join(self.tmp, "file", "x.sqlite3"))
        with open(os.path.join(self.tmp, "file"), "w") as handle:
            handle.write("not a directory")
        self.assertEqual(self.client.get(f"/sonar/r/{LOG_ID}", headers={"User-Agent": SAFARI}).status_code, 200)
        self.assertEqual(self.client.get("/sonar/go?to=appstore", headers={"User-Agent": SAFARI}).status_code, 302)

    # --- The redirect --------------------------------------------------------------------

    def test_go_redirects_and_counts(self):
        headers = {"User-Agent": SAFARI}
        store = self.client.get("/sonar/go?to=appstore&k=profile&s=profile&u=/sonar/u/maya", headers=headers)
        self.assertEqual(store.status_code, 302)
        self.assertEqual(store.headers["Location"], "https://apps.apple.com/app/id6761410303")
        self.assertEqual(store.headers["Cache-Control"], "no-store")
        self.assertIn("noindex", store.headers["X-Robots-Tag"])

        cases = {
            f"/sonar/r/{LOG_ID}": f"sonar://review/{LOG_ID}",
            "/sonar/e/387129/60827464893": "sonar://episode/387129/60827464893",
            "/sonar/p/387129": "sonar://podcast/387129",
            "/sonar/u/maya.listens": "sonar://user/maya.listens",
            "/sonar/l/0b6f1c2e-4a5d-4e8f-9a1b-2c3d4e5f6a7b": "sonar://list/0b6f1c2e-4a5d-4e8f-9a1b-2c3d4e5f6a7b",
            "/sonar/i/maya.listens": "sonar://invite/maya.listens",
        }
        for path, link in cases.items():
            response = self.client.get("/sonar/go", query_string={"to": "app", "k": "list", "s": "story", "u": path},
                                       headers=headers)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.headers["Location"], link, path)

        clicks = self._clicks()
        # The kind comes from the validated path, not from k.
        self.assertIn(("profile", "profile", "appstore", 1), clicks)
        self.assertIn(("review", "story", "app", 1), clicks)
        self.assertIn(("invite", "story", "app", 1), clicks)
        self.assertEqual(sum(row[3] for row in clicks), 7)

    def test_go_rejects_open_redirects_and_bad_targets(self):
        headers = {"User-Agent": SAFARI}
        bad = [
            {"to": "https://evil.example"},
            {"to": "javascript:alert(1)"},
            {"to": ""},
            {},
            {"to": "app"},
            {"to": "app", "u": "https://evil.example/sonar/r/" + LOG_ID},
            {"to": "app", "u": "//evil.example"},
            {"to": "app", "u": "/sonar/r/" + LOG_ID + "/../../evil"},
            {"to": "app", "u": "/sonar/r/" + LOG_ID + "\n"},
            {"to": "app", "u": "/sonar/u/maya?x=1"},
            {"to": "app", "u": "/sonar/u/maya/../../evil"},
            {"to": "app", "u": "/sonar/u/ma%2Fya"},
            {"to": "app", "u": "/sonar/go"},
            {"to": "app", "u": "/sonar/og/r/" + LOG_ID + ".png"},
            {"to": "app", "u": "sonar://review/" + LOG_ID},
            {"to": "app", "u": "javascript:alert(1)"},
        ]
        for query in bad:
            response = self.client.get("/sonar/go", query_string=query, headers=headers)
            self.assertEqual(response.status_code, 400, query)
            self.assertNotIn("Location", response.headers, query)
        # The App Store target ignores a hostile path: it always goes to the one App Store URL.
        response = self.client.get("/sonar/go", query_string={"to": "appstore", "u": "https://evil.example"}, headers=headers)
        self.assertEqual(response.headers["Location"], "https://apps.apple.com/app/id6761410303")
        self.assertEqual(self._clicks(), [("unknown", "unknown", "appstore", 1)])

    def test_share_target_only_accepts_share_paths(self):
        from app.blueprints.sonar_share.routes import share_target
        self.assertEqual(share_target(f"/sonar/r/{LOG_ID}"), ("review", f"sonar://review/{LOG_ID}"))
        for path in ("", None, "/sonar/r/x", "/sonar/u/" + "a" * 31, "/sonar/e/1", "/sonar/r/" + LOG_ID + "/"):
            self.assertIsNone(share_target(path), path)

    # --- Admin ---------------------------------------------------------------------------

    def test_stats_page_requires_admin(self):
        response = self.client.get("/admin/sonar")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

    def test_stats_page_shows_views_clicks_and_click_through(self):
        headers = {"User-Agent": SAFARI}
        for _ in range(4):
            self.client.get(f"/sonar/r/{LOG_ID}?s=story", headers=headers)
        self.client.get(f"/sonar/go?to=app&s=story&u=/sonar/r/{LOG_ID}", headers=headers)
        self.client.get(f"/sonar/go?to=appstore&k=review&s=story&u=/sonar/r/{LOG_ID}", headers=headers)
        self.client.get("/sonar/i/maya?s=invite", headers=headers)

        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
        response = self.client.get("/admin/sonar")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("Last 7 days", html)
        self.assertIn("Last 30 days", html)
        self.assertIn('<td data-label="Click-through">50.0%</td>', html)
        self.assertIn('<td data-label="Click-through">0.0%</td>', html)  # the invite: a view, no taps
        self.assertIn(">story<", html)

        summary = None
        with self.app.app_context():
            summary = attribution.summary(7)
        top = summary["rows"][0]
        self.assertEqual((top["kind"], top["source"], top["views"], top["app"], top["appstore"]), ("review", "story", 4, 1, 1))
        self.assertEqual(summary["totals"]["views"], 5)
        self.assertAlmostEqual(summary["totals"]["ctr"], 0.4)

    def test_summary_window(self):
        with self.app.app_context():
            attribution.record_view("review", "story")
            with attribution.database() as connection:
                connection.execute("INSERT INTO sonar_share_views VALUES ('2000-01-01', 'review', 'story', 50)")
            self.assertEqual(attribution.summary(7)["totals"]["views"], 1)
            self.assertEqual(attribution.summary(30)["totals"]["views"], 1)


if __name__ == "__main__":
    unittest.main()
