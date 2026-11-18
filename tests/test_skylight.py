import unittest

from app import create_app


class SkylightPagesTests(unittest.TestCase):
    """App Store Connect links to /skylight/privacy and /skylight/support, so they must keep answering."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-only")
        self.client = self.app.test_client()

    def test_pages_render_with_their_tabs(self):
        for path, heading in [
            ("/skylight", "Skylight"),
            ("/skylight/support", "Skylight support"),
            ("/skylight/privacy", "Skylight privacy policy"),
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            html = response.get_data(as_text=True)
            self.assertIn(f">{heading}</h1>", html, path)
            self.assertIn('aria-label="Skylight pages"', html, path)
            self.assertIn('href="/skylight/privacy"', html, path)
            self.assertIn('href="/skylight/support"', html, path)

    def test_trailing_slashes_work(self):
        for path in ("/skylight/", "/skylight/support/", "/skylight/privacy/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
