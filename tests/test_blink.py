import unittest

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

    def test_privacy_policy_covers_what_review_checks(self):
        html = self.client.get("/blink/privacy").get_data(as_text=True)
        for phrase in ("encrypt", "CloudKit", "deleted", "report", "camera", "contact page"):
            self.assertIn(phrase.lower(), html.lower(), phrase)


if __name__ == "__main__":
    unittest.main()
