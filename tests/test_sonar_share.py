import json
import unittest
from unittest import mock

from app import create_app
from app.blueprints.sonar_share import data


class SonarShareTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()
        data._cache.clear()

    def test_apple_app_site_association_lists_share_paths(self):
        for path in ("/.well-known/apple-app-site-association", "/apple-app-site-association"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(response.mimetype, "application/json")
            details = json.loads(response.data)["applinks"]["details"][0]
            self.assertEqual(details["appIDs"], ["9A9HR6WT4K.com.jeremyzay.Sonar"])
            paths = {c["/"] for c in details["components"]}
            self.assertEqual(paths, {"/sonar/r/*", "/sonar/e/*", "/sonar/p/*", "/sonar/u/*"})
            # The marketing pages must keep opening in Safari.
            self.assertNotIn("/sonar", paths)
            self.assertNotIn("/sonar/*", paths)

    def test_review_page_renders_preview_and_actions(self):
        show = data.Podcast(id="1", name="Radiolab", author="WNYC", artwork="https://img/show.jpg")
        episode = data.Episode(id="2", title="Grass Apes", artwork="https://img/ep.jpg", podcast=show)
        review = data.Review(
            id="d351c000-0000-4000-8003-000000000000", username="maya.listens", rating=9,
            is_loved=True, text="Loved it.", episode=episode,
        )
        with mock.patch.object(data, "review", return_value=review):
            response = self.client.get(f"/sonar/r/{review.id}")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Grass Apes", html)
        self.assertIn("Loved it.", html)
        self.assertIn("@maya.listens", html)
        self.assertIn('property="og:image" content="https://img/ep.jpg"', html)
        self.assertIn(f'href="sonar://review/{review.id}"', html)
        self.assertIn("apps.apple.com/app/id6761410303", html)
        self.assertIn('name="apple-itunes-app"', html)

    def test_missing_content_still_offers_the_app(self):
        with mock.patch.object(data, "review", return_value=None):
            response = self.client.get("/sonar/r/d351c000-0000-4000-8003-000000000000")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Open in Sonar", response.get_data(as_text=True))

    def test_episode_podcast_and_profile_pages(self):
        show = data.Podcast(id="387129", name="Planet Money", author="NPR", artwork=None, description="<p>Money.</p>")
        episode = data.Episode(id="60827464893", title="Tariffs", artwork=None, podcast=show)
        with mock.patch.object(data, "episode", return_value=episode), \
                mock.patch.object(data, "community_average", return_value=4.5):
            html = self.client.get("/sonar/e/387129/60827464893").get_data(as_text=True)
        self.assertIn("Tariffs", html)
        self.assertIn("4.5 on Sonar", html)
        self.assertIn('href="sonar://episode/387129/60827464893"', html)

        with mock.patch.object(data, "podcast", return_value=show):
            html = self.client.get("/sonar/p/387129").get_data(as_text=True)
        self.assertIn("Planet Money", html)

        with mock.patch.object(data, "profile", return_value=data.Profile(username="maya.listens", logged_count=12)):
            html = self.client.get("/sonar/u/maya.listens").get_data(as_text=True)
        self.assertIn("@maya.listens", html)
        self.assertIn("12 episodes logged", html)

    def test_lookups_reject_malformed_ids_without_network(self):
        with mock.patch.object(data.requests, "get") as get:
            self.assertIsNone(data.review("not-a-uuid"))
            self.assertIsNone(data.episode("12a"))
            self.assertIsNone(data.podcast("../etc"))
            self.assertIsNone(data.profile("bad name!"))
            get.assert_not_called()

    def test_bad_username_is_404(self):
        self.assertEqual(self.client.get("/sonar/u/bad%20name!").status_code, 404)

    def test_existing_sonar_pages_unchanged(self):
        for path in ("/sonar", "/sonar/privacy", "/sonar/support"):
            self.assertEqual(self.client.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
