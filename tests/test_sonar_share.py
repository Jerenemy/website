import html as html_lib
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from PIL import Image

from app import create_app
from app.blueprints.sonar_share import data, og

LOG_ID = "d351c000-0000-4000-8003-000000000000"
LIST_ID = "0b6f1c2e-4a5d-4e8f-9a1b-2c3d4e5f6a7b"
USER_ID = "5e1f0000-0000-4000-8000-000000000001"
REAL_FETCH_ARTWORK = og.fetch_artwork  # setUp mocks it; the guard tests call the real one


def _artwork(color=(200, 60, 50)):
    return Image.new("RGB", (600, 600), color)


def _sample_review():
    show = data.Podcast(id="1", name="Radiolab", author="WNYC", artwork="https://img/show.jpg")
    episode = data.Episode(id="2", title="Grass Apes", artwork="https://img/ep.jpg", podcast=show)
    return data.Review(id=LOG_ID, username="maya.listens", rating=9, is_loved=True, text="Loved it.", episode=episode)


def _sample_list(items=None, count=2):
    if items is None:
        items = [
            data.ListItem(kind="episode", podcast_id="1", episode_id="2", note="Start here",
                          episode=data.Episode(id="2", title="Grass Apes", artwork="https://img/ep.jpg",
                                               podcast=data.Podcast(id="1", name="Radiolab"))),
            data.ListItem(kind="podcast", podcast_id="387129",
                          podcast=data.Podcast(id="387129", name="Planet Money", author="NPR", artwork="https://img/pm.jpg")),
        ]
    return data.SonarList(id=LIST_ID, title="Road trip listening", description="Long drives only.",
                          username="maya.listens", item_count=count, items=items)


def _sample_page(**changes):
    review = _sample_review()
    review.user_id = "u1"
    favorite = data.ListItem(kind="podcast", podcast_id="387129",
                             podcast=data.Podcast(id="387129", name="Planet Money", artwork="https://img/pm.jpg"))
    values = dict(
        profile=data.Profile(username="maya.listens", logged_count=128, id="u1"),
        avatar_url=None,
        followers=34,
        following=21,
        favorites=[favorite],
        recent_reviews=[review],
        lists=[data.ListSummary(id=LIST_ID, title="Road trip listening", item_count=14)],
    )
    values.update(changes)
    return data.ProfilePage(**values)


class _FakeResponse:
    def __init__(self, rows, headers=None):
        self._rows = rows
        self.headers = headers or {}

    def json(self):
        return self._rows


class SonarShareTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.cache_dir = tempfile.mkdtemp()
        self.app.config.update(
            TESTING=True,
            SONAR_OG_CACHE_DIR=self.cache_dir,
            SONAR_STATS_DATABASE_PATH=os.path.join(self.cache_dir, "stats.sqlite3"),
        )
        self.client = self.app.test_client()
        data._cache.clear()
        og.clear_memory_cache()
        # No test reaches the network: artwork comes from here.
        patcher = mock.patch.object(og, "fetch_artwork", side_effect=lambda url: _artwork())
        self.fetch_artwork = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def _button(self, html, label):
        """The href of a call-to-action button, unescaped."""
        match = re.search(r'<a class="button[^"]*" href="([^"]+)">' + re.escape(label) + "</a>", html)
        return html_lib.unescape(match.group(1)) if match else None

    def _open_in_sonar(self, html, label="Open in Sonar"):
        """Follows the page's "Open in Sonar" button through /sonar/go; returns the app link."""
        href = self._button(html, label)
        self.assertIsNotNone(href, "no Open in Sonar button")
        if href.startswith("sonar://"):
            return href
        response = self.client.get(href, headers={"User-Agent": "Mozilla/5.0 (iPhone) Safari/604.1"})
        self.assertEqual(response.status_code, 302, href)
        return response.headers["Location"]

    def test_apple_app_site_association_lists_share_paths(self):
        for path in ("/.well-known/apple-app-site-association", "/apple-app-site-association"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(response.mimetype, "application/json")
            details = json.loads(response.data)["applinks"]["details"][0]
            self.assertEqual(details["appIDs"], ["9A9HR6WT4K.com.jeremyzay.Sonar"])
            paths = {c["/"] for c in details["components"]}
            self.assertEqual(paths, {"/sonar/r/*", "/sonar/e/*", "/sonar/p/*", "/sonar/u/*", "/sonar/l/*", "/sonar/i/*"})
            # Nor is the attribution redirect.
            self.assertNotIn("/sonar/go", paths)
            # Preview images are plain files, never app links.
            self.assertFalse(any(p.startswith("/sonar/og") for p in paths))
            # The marketing pages must keep opening in Safari.
            self.assertNotIn("/sonar", paths)
            self.assertNotIn("/sonar/*", paths)

    def test_review_page_renders_preview_and_actions(self):
        review = _sample_review()
        with mock.patch.object(data, "review", return_value=review):
            response = self.client.get(f"/sonar/r/{review.id}")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Grass Apes", html)
        self.assertIn("Loved it.", html)
        self.assertIn("@maya.listens", html)
        self.assertIn(f'property="og:image" content="http://localhost/sonar/og/r/{review.id}.png"', html)
        self.assertIn(f'name="twitter:image" content="http://localhost/sonar/og/r/{review.id}.png"', html)
        self.assertIn('property="og:image:width" content="1200"', html)
        self.assertIn('property="og:image:height" content="630"', html)
        self.assertIn('name="twitter:card" content="summary_large_image"', html)
        self.assertEqual(self._open_in_sonar(html), f"sonar://review/{review.id}")
        self.assertEqual(self._open_in_sonar(html, "Get Sonar on the App Store"), "https://apps.apple.com/app/id6761410303")
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
                mock.patch.object(data, "community_rating", return_value=(4.5, 12)):
            html = self.client.get("/sonar/e/387129/60827464893").get_data(as_text=True)
        self.assertIn("Tariffs", html)
        self.assertIn("<strong>4.5</strong> on Sonar · 12 ratings", html)
        self.assertEqual(self._open_in_sonar(html), "sonar://episode/387129/60827464893")

        with mock.patch.object(data, "podcast", return_value=show):
            html = self.client.get("/sonar/p/387129").get_data(as_text=True)
        self.assertIn("Planet Money", html)

        page = data.ProfilePage(profile=data.Profile(username="maya.listens", logged_count=12, id="u1"))
        with mock.patch.object(data, "profile_page", return_value=page):
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

    def test_og_meta_points_at_generated_images(self):
        show = data.Podcast(id="387129", name="Planet Money")
        episode = data.Episode(id="60827464893", title="Tariffs", podcast=show)
        cases = [
            ("/sonar/e/387129/60827464893", "/sonar/og/e/387129/60827464893.png",
             mock.patch.object(data, "episode", return_value=episode)),
            ("/sonar/p/387129", "/sonar/og/p/387129.png", mock.patch.object(data, "podcast", return_value=show)),
            ("/sonar/u/maya.listens", "/sonar/og/u/maya.listens.png",
             mock.patch.object(data, "profile_page",
                               return_value=data.ProfilePage(profile=data.Profile(username="maya.listens", id="u1")))),
            (f"/sonar/l/{LIST_ID}", f"/sonar/og/l/{LIST_ID}.png",
             mock.patch.object(data, "sonar_list", return_value=_sample_list())),
        ]
        for path, image, patch in cases:
            with patch, mock.patch.object(data, "community_average", return_value=None):
                html = self.client.get(path).get_data(as_text=True)
            self.assertIn(f'property="og:image" content="http://localhost{image}"', html, path)
            self.assertIn('property="og:image:width" content="1200"', html, path)

    def test_missing_pages_point_at_an_image_that_falls_back(self):
        with mock.patch.object(data, "review", return_value=None):
            html = self.client.get(f"/sonar/r/{LOG_ID}").get_data(as_text=True)
        self.assertIn(f"/sonar/og/r/{LOG_ID}.png", html)
        with mock.patch.object(data, "review", return_value=None):
            html = self.client.get("/sonar/r/not-a-uuid").get_data(as_text=True)
        self.assertIn("/sonar/og/brand.png", html)

    # --- Open Graph images ---------------------------------------------------------------

    def _assert_png(self, response, size=(1200, 630)):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        image = Image.open(io.BytesIO(response.data))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, size)
        return image

    def test_og_images_render_for_every_kind(self):
        review = _sample_review()
        show = review.episode.podcast
        cases = [
            (f"/sonar/og/r/{LOG_ID}.png", mock.patch.object(data, "review", return_value=review)),
            ("/sonar/og/e/1/2.png", mock.patch.object(data, "episode", return_value=review.episode)),
            ("/sonar/og/p/1.png", mock.patch.object(data, "podcast", return_value=show)),
            ("/sonar/og/u/maya.listens.png",
             mock.patch.object(data, "profile_page", return_value=data.ProfilePage(
                 profile=data.Profile(username="maya.listens", logged_count=3, id="u1")))),
            ("/sonar/og/i/maya.listens.png", mock.patch.object(data, "profile_page", return_value=_sample_page())),
            (f"/sonar/og/l/{LIST_ID}.png", mock.patch.object(data, "sonar_list", return_value=_sample_list())),
            ("/sonar/og/brand.png", mock.patch.object(data, "review", return_value=None)),
        ]
        for path, patch in cases:
            with patch, mock.patch.object(data, "community_average", return_value=4.5):
                response = self.client.get(path)
            self._assert_png(response)
            self.assertIn("max-age=86400", response.headers["Cache-Control"], path)
            self.assertTrue(response.headers.get("ETag"), path)

    def test_og_review_with_long_text_and_no_rating(self):
        review = _sample_review()
        review.rating = None
        review.text = "word " * 400 + "😀 中文"
        with mock.patch.object(data, "review", return_value=review):
            self._assert_png(self.client.get(f"/sonar/og/r/{LOG_ID}.png"))

    def test_og_image_is_cached(self):
        with mock.patch.object(data, "review", return_value=_sample_review()) as lookup:
            first = self.client.get(f"/sonar/og/r/{LOG_ID}.png")
            og.clear_memory_cache()  # the disk cache answers next
            second = self.client.get(f"/sonar/og/r/{LOG_ID}.png")
            third = self.client.get(f"/sonar/og/r/{LOG_ID}.png")
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(first.data, second.data)
        self.assertEqual(second.data, third.data)
        conditional = self.client.get(f"/sonar/og/r/{LOG_ID}.png", headers={"If-None-Match": first.headers["ETag"]})
        self.assertEqual(conditional.status_code, 304)

    def test_og_falls_back_to_brand_image_when_lookup_fails(self):
        brand = self.client.get("/sonar/og/brand.png").data
        with mock.patch.object(data, "review", return_value=None):
            missing = self.client.get(f"/sonar/og/r/{LOG_ID}.png")
        self._assert_png(missing)
        self.assertEqual(missing.data, brand)
        self.assertEqual(missing.headers["Cache-Control"], og.CACHE_CONTROL_SHORT)

        with mock.patch.object(data, "podcast", side_effect=RuntimeError("boom")):
            broken = self.client.get("/sonar/og/p/1.png")
        self._assert_png(broken)
        self.assertEqual(broken.data, brand)

        # Real lookups with Supabase / Podcast Index failing also end at the brand image.
        self.app.config.update(SONAR_SUPABASE_URL="https://example.supabase.co", SONAR_SUPABASE_ANON_KEY="anon")
        with mock.patch.object(data.requests, "get", side_effect=data.requests.ConnectionError("down")):
            response = self.client.get(f"/sonar/og/l/{LIST_ID}.png")
        self.assertEqual(response.data, brand)

    def test_og_artwork_failure_still_renders_but_is_not_cached_long(self):
        self.fetch_artwork.side_effect = og.ArtworkError("timeout")
        with mock.patch.object(data, "review", return_value=_sample_review()):
            response = self.client.get(f"/sonar/og/r/{LOG_ID}.png")
        self._assert_png(response)
        self.assertEqual(response.headers["Cache-Control"], og.CACHE_CONTROL_SHORT)
        self.assertEqual(os.listdir(self.cache_dir), [])

    def test_og_invalid_ids_are_404(self):
        with mock.patch.object(data.requests, "get") as get:
            for path in (
                "/sonar/og/r/not-a-uuid.png",
                "/sonar/og/e/12a/3.png",
                "/sonar/og/e/1/x.png",
                "/sonar/og/p/abc.png",
                "/sonar/og/u/bad%20name!.png",
                "/sonar/og/l/nope.png",
                f"/sonar/og/l/{LIST_ID}.jpg",
            ):
                self.assertEqual(self.client.get(path).status_code, 404, path)
            get.assert_not_called()

    # --- Artwork fetching ----------------------------------------------------------------

    def test_fetch_artwork_guards(self):
        fetch = REAL_FETCH_ARTWORK
        with mock.patch.object(og.requests, "get") as get:
            for url in ("http://127.0.0.1:5003/x.png", "http://localhost/x.png", "file:///etc/passwd",
                        "ftp://example.com/a.png", "http://10.0.0.5/a.jpg", "http://[::1]/a.jpg", ""):
                with self.assertRaises(og.ArtworkError, msg=url):
                    fetch(url)
            get.assert_not_called()

        public = [(2, 1, 6, "", ("93.184.216.34", 0))]
        private = [(2, 1, 6, "", ("192.168.1.1", 0))]

        def response(status=200, headers=None, body=b""):
            fake = mock.MagicMock()
            fake.status_code = status
            fake.headers = headers or {}
            fake.is_redirect = status in (301, 302, 303, 307, 308)
            fake.iter_content.return_value = [body[i:i + 1024] for i in range(0, len(body), 1024)] or [b""]
            fake.__enter__.return_value = fake
            return fake

        # A redirect to an internal address is refused before it is followed.
        with mock.patch.object(og.socket, "getaddrinfo", side_effect=[public, private]), \
                mock.patch.object(og.requests, "get", return_value=response(302, {"Location": "http://intranet/a.jpg"})) as get:
            with self.assertRaises(og.ArtworkError):
                fetch("https://cdn.example.com/a.jpg")
            self.assertEqual(get.call_count, 1)

        # Too large, declared or streamed.
        with mock.patch.object(og.socket, "getaddrinfo", return_value=public), \
                mock.patch.object(og.requests, "get", return_value=response(headers={"Content-Length": str(50 * 1024 * 1024)})):
            with self.assertRaises(og.ArtworkError):
                fetch("https://cdn.example.com/a.jpg")
        with mock.patch.object(og.socket, "getaddrinfo", return_value=public), \
                mock.patch.object(og, "ARTWORK_MAX_BYTES", 4096), \
                mock.patch.object(og.requests, "get", return_value=response(body=b"x" * 10000)):
            with self.assertRaises(og.ArtworkError):
                fetch("https://cdn.example.com/a.jpg")

        # Not an image.
        with mock.patch.object(og.socket, "getaddrinfo", return_value=public), \
                mock.patch.object(og.requests, "get", return_value=response(body=b"<html></html>")):
            with self.assertRaises(og.ArtworkError):
                fetch("https://cdn.example.com/a.jpg")

        # A real image decodes.
        buffer = io.BytesIO()
        _artwork().save(buffer, "JPEG")
        with mock.patch.object(og.socket, "getaddrinfo", return_value=public), \
                mock.patch.object(og.requests, "get", return_value=response(body=buffer.getvalue())):
            image = fetch("https://cdn.example.com/a.jpg")
        self.assertEqual(image.mode, "RGB")

    # --- Lists ---------------------------------------------------------------------------

    def test_list_page_renders_entries_and_actions(self):
        with mock.patch.object(data, "sonar_list", return_value=_sample_list(count=14)):
            response = self.client.get(f"/sonar/l/{LIST_ID}")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Road trip listening", html)
        self.assertIn("Long drives only.", html)
        self.assertIn("@maya.listens", html)
        self.assertIn("Grass Apes", html)
        self.assertIn("Start here", html)
        self.assertIn("Planet Money", html)
        self.assertIn('src="https://img/pm.jpg"', html)
        self.assertIn('href="/sonar/e/1/2"', html)
        self.assertIn('href="/sonar/p/387129"', html)
        self.assertIn("And 12 more in Sonar.", html)
        self.assertEqual(self._open_in_sonar(html), f"sonar://list/{LIST_ID}")
        self.assertEqual(self._open_in_sonar(html, "Get Sonar on the App Store"), "https://apps.apple.com/app/id6761410303")
        self.assertIn(f'app-argument=http://localhost/sonar/l/{LIST_ID}', html)

    def test_private_or_missing_list_is_a_friendly_404(self):
        with mock.patch.object(data, "sonar_list", return_value=None):
            response = self.client.get(f"/sonar/l/{LIST_ID}")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Open in Sonar", html)
        self.assertEqual(self._open_in_sonar(html), f"sonar://list/{LIST_ID}")
        self.assertIn("private or deleted", html)

        with mock.patch.object(data.requests, "get") as get:
            response = self.client.get("/sonar/l/not-a-list")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Open in Sonar", response.get_data(as_text=True))
        get.assert_not_called()

    def test_sonar_list_lookup_reads_only_public_lists(self):
        calls = []

        def supabase(path, params, headers=None):
            calls.append((path, params))
            if path == "lists":
                return _FakeResponse([{"id": LIST_ID, "user_id": "u1", "title": " Road trip ", "description": ""}])
            if path == "profiles":
                return _FakeResponse([{"username": "maya.listens"}])
            return _FakeResponse(
                [
                    {"kind": "episode", "podcast_id": "1", "episode_id": "2", "note": " Start here "},
                    {"kind": "podcast", "podcast_id": "387129", "episode_id": None, "note": None},
                    {"kind": "episode", "podcast_id": "../x", "episode_id": "2", "note": None},  # dropped
                ],
                headers={"Content-Range": "0-2/31"},
            )

        episode = data.Episode(id="2", title="Grass Apes")
        show = data.Podcast(id="387129", name="Planet Money")
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=supabase), \
                mock.patch.object(data, "episode", return_value=episode), \
                mock.patch.object(data, "podcast", return_value=show):
            item = data.sonar_list(LIST_ID)
        self.assertEqual(calls[0][1]["is_public"], "eq.true")
        self.assertEqual(calls[0][1]["id"], f"eq.{LIST_ID}")
        self.assertEqual(item.title, "Road trip")
        self.assertIsNone(item.description)
        self.assertEqual(item.username, "maya.listens")
        self.assertEqual(item.item_count, 31)
        self.assertEqual([entry.title for entry in item.items], ["Grass Apes", "Planet Money"])
        self.assertEqual(item.items[0].note, "Start here")

        with self.app.app_context(), mock.patch.object(data, "_supabase", return_value=_FakeResponse([])):
            data._cache.clear()
            self.assertIsNone(data.sonar_list(LIST_ID))
        with mock.patch.object(data.requests, "get") as get:
            self.assertIsNone(data.sonar_list("nope"))
            get.assert_not_called()

    # --- Tier 2: richer pages, invites ---------------------------------------------------

    def _json_ld(self, html):
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(match, "no JSON-LD")
        return json.loads(match.group(1))

    def test_profile_page_renders_every_readable_section(self):
        page = _sample_page(avatar_url="https://example.supabase.co/storage/v1/object/public/avatars/u1/avatar.jpg?v=1")
        with mock.patch.object(data, "profile_page", return_value=page):
            html = self.client.get("/sonar/u/maya.listens").get_data(as_text=True)
        self.assertIn('src="https://example.supabase.co/storage/v1/object/public/avatars/u1/avatar.jpg?v=1"', html)
        self.assertIn("<strong>128</strong><span>logged</span>", html)
        self.assertIn("<strong>34</strong><span>followers</span>", html)
        self.assertIn("<strong>21</strong><span>following</span>", html)
        self.assertIn(">Favorites<", html)
        self.assertIn('href="/sonar/p/387129"', html)
        self.assertIn(">Recent reviews<", html)
        self.assertIn(f'href="/sonar/r/{LOG_ID}"', html)
        self.assertIn("Loved it.", html)
        self.assertIn(">Lists<", html)
        self.assertIn(f'href="/sonar/l/{LIST_ID}"', html)
        self.assertIn('name="description" content="@maya.listens rates and reviews podcast episodes on Sonar. '
                      '128 episodes logged · 34 followers. Latest: Grass Apes (Radiolab)."', html)
        ld = self._json_ld(html)
        self.assertEqual(ld["@type"], "ProfilePage")
        self.assertEqual(ld["mainEntity"]["alternateName"], "maya.listens")
        self.assertEqual(ld["mainEntity"]["interactionStatistic"][0]["userInteractionCount"], 34)

    def test_profile_page_hides_sections_the_public_key_cannot_read(self):
        page = _sample_page(followers=None, following=None, favorites=None, lists=None, recent_reviews=[])
        with mock.patch.object(data, "profile_page", return_value=page):
            html = self.client.get("/sonar/u/maya.listens").get_data(as_text=True)
        for hidden in (">Favorites<", ">Lists<", ">Recent reviews<", "followers</span>", "class=\"stats\""):
            self.assertNotIn(hidden, html)
        self.assertIn("128 episodes logged on Sonar", html)
        self.assertIn('class="avatar avatar--large"', html)  # the initial, no photo

    def test_review_page_shows_more_from_the_reviewer_and_counts(self):
        review = _sample_review()
        review.like_count, review.reply_count, review.created_at = 7, 1, "2026-10-01T12:00:00+00:00"
        other = _sample_review()
        other.id = "aaaaaaaa-0000-4000-8000-000000000000"
        other.text = "Second one."
        with mock.patch.object(data, "review", return_value=review), \
                mock.patch.object(data, "more_reviews", return_value=[other]) as more:
            html = self.client.get(f"/sonar/r/{LOG_ID}").get_data(as_text=True)
        more.assert_called_once_with(review)
        self.assertIn("<strong>7</strong> likes", html)
        self.assertIn("<strong>1</strong> reply", html)
        self.assertIn("More from @maya.listens", html)
        self.assertIn(f'href="/sonar/r/{other.id}"', html)
        self.assertIn("Second one.", html)
        ld = self._json_ld(html)
        self.assertEqual(ld["@type"], "Review")
        self.assertEqual(ld["reviewRating"]["ratingValue"], 4.5)
        self.assertEqual(ld["author"]["url"], "http://localhost/sonar/u/maya.listens")
        self.assertEqual(ld["itemReviewed"]["@type"], "PodcastEpisode")
        self.assertEqual(ld["itemReviewed"]["partOfSeries"]["name"], "Radiolab")
        self.assertEqual(ld["datePublished"], "2026-10-01")

    def test_review_page_without_counts_or_more(self):
        with mock.patch.object(data, "review", return_value=_sample_review()), \
                mock.patch.object(data, "more_reviews", return_value=[]):
            html = self.client.get(f"/sonar/r/{LOG_ID}").get_data(as_text=True)
        self.assertNotIn("More from", html)
        self.assertNotIn('class="social"', html)

    def test_episode_page_shows_community_reviews_and_average(self):
        show = data.Podcast(id="1", name="Radiolab")
        episode = data.Episode(id="2", title="Grass Apes", podcast=show)
        reviewer = data.Review(id=LOG_ID, username="sam", rating=8, is_loved=False, text="So good.", episode=None)
        with mock.patch.object(data, "episode", return_value=episode), \
                mock.patch.object(data, "community_rating", return_value=(4.2, 3)), \
                mock.patch.object(data, "episode_reviews", return_value=[reviewer]):
            html = self.client.get("/sonar/e/1/2").get_data(as_text=True)
        self.assertIn("What listeners say", html)
        self.assertIn("@sam", html)
        self.assertIn("So good.", html)
        self.assertIn(f'href="/sonar/r/{LOG_ID}"', html)
        self.assertIn("Rated 4.2/5 by 3 listeners on Sonar", html)
        ld = self._json_ld(html)
        self.assertEqual(ld["@type"], "PodcastEpisode")
        self.assertEqual(ld["aggregateRating"]["ratingValue"], 4.2)
        self.assertEqual(ld["aggregateRating"]["ratingCount"], 3)
        self.assertEqual(ld["review"][0]["reviewBody"], "So good.")

    def test_invite_page_for_a_known_user(self):
        with mock.patch.object(data, "profile_page", return_value=_sample_page()):
            response = self.client.get("/sonar/i/maya.listens?s=invite")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>@maya.listens invited you to Sonar · Sonar</title>", html)
        self.assertIn("invited you to Sonar", html)
        self.assertIn("Loved it.", html)
        self.assertIn("@maya.listens&#39;s favorites", html)
        self.assertIn('content="app-id=6761410303, app-argument=http://localhost/sonar/i/maya.listens"', html)
        self.assertIn('property="og:image" content="http://localhost/sonar/og/i/maya.listens.png"', html)
        self.assertIn('<link rel="canonical" href="http://localhost/sonar/i/maya.listens">', html)
        # The App Store comes first on an invite; the app link is the invite deep link.
        self.assertLess(html.index("Get Sonar on the App Store"), html.index("Already have it? Open in Sonar"))
        self.assertEqual(self._open_in_sonar(html, "Already have it? Open in Sonar"), "sonar://invite/maya.listens")
        self.assertEqual(self._open_in_sonar(html, "Get Sonar on the App Store"), "https://apps.apple.com/app/id6761410303")

    def test_invite_page_for_an_unknown_or_malformed_user_is_friendly(self):
        with mock.patch.object(data, "profile_page", return_value=None):
            response = self.client.get("/sonar/i/nobody_here")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("You're invited to Sonar", html)
        self.assertEqual(self._open_in_sonar(html, "Already have it? Open in Sonar"), "sonar://invite/nobody_here")

        with mock.patch.object(data.requests, "get") as get:
            response = self.client.get("/sonar/i/bad%20name!")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("You're invited to Sonar", html)
        self.assertNotIn("Open in Sonar", html)
        self.assertIn("/sonar/og/brand.png", html)
        get.assert_not_called()

    def test_source_parameter_never_changes_routing_or_canonical(self):
        review = _sample_review()
        with mock.patch.object(data, "review", return_value=review) as lookup, \
                mock.patch.object(data, "more_reviews", return_value=[]):
            plain = self.client.get(f"/sonar/r/{LOG_ID}").get_data(as_text=True)
            tagged = self.client.get(f"/sonar/r/{LOG_ID}?s=story").get_data(as_text=True)
            odd = self.client.get(f"/sonar/r/{LOG_ID}?s=%3Cscript%3E").get_data(as_text=True)
        self.assertEqual({call.args for call in lookup.call_args_list}, {(LOG_ID,)})
        for html in (plain, tagged, odd):
            self.assertIn(f'<link rel="canonical" href="http://localhost/sonar/r/{LOG_ID}">', html)
            self.assertIn(f'property="og:url" content="http://localhost/sonar/r/{LOG_ID}"', html)
            self.assertIn(f"app-argument=http://localhost/sonar/r/{LOG_ID}\"", html)
            self.assertNotIn("<script>", html.split("</head>")[1])
        self.assertIn("s=story", self._button(tagged, "Open in Sonar"))
        self.assertIn("s=unknown", self._button(plain, "Open in Sonar"))
        self.assertIn("s=unknown", self._button(odd, "Open in Sonar"))

    def test_og_invite_image(self):
        with mock.patch.object(data, "profile_page", return_value=_sample_page(
                avatar_url="https://example.supabase.co/storage/v1/object/public/avatars/u1/avatar.jpg")):
            response = self.client.get("/sonar/og/i/maya.listens.png")
        self._assert_png(response)
        self.assertIn("max-age=86400", response.headers["Cache-Control"])
        self.assertIn("https://example.supabase.co/storage/v1/object/public/avatars/u1/avatar.jpg",
                      [call.args[0] for call in self.fetch_artwork.call_args_list])

        og.clear_memory_cache()
        with mock.patch.object(data, "profile_page", return_value=None):
            generic = self.client.get("/sonar/og/i/somebody.png")
        self._assert_png(generic)
        self.assertEqual(generic.headers["Cache-Control"], og.CACHE_CONTROL_SHORT)
        self.assertNotEqual(generic.data, self.client.get("/sonar/og/brand.png").data)
        self.assertEqual(self.client.get("/sonar/og/i/bad%20name!.png").status_code, 404)

    # --- Tier 2 lookups ------------------------------------------------------------------

    def _supabase_double(self, tables):
        """A fake _supabase: tables maps path -> rows, a (rows, headers) pair, or an exception."""
        calls = []

        def fake(path, params, headers=None):
            calls.append((path, params))
            value = tables.get(path, [])
            if callable(value):
                value = value(params)
            if isinstance(value, Exception):
                raise value
            if isinstance(value, tuple):
                return _FakeResponse(*value)
            return _FakeResponse(value)

        return fake, calls

    def _denied(self):
        response = mock.MagicMock(status_code=401)
        return data.requests.HTTPError("401 permission denied", response=response)

    def test_profile_page_lookup_hides_what_rls_refuses(self):
        rows = [{"id": LOG_ID, "user_id": "u1", "episode_id": "2", "podcast_id": "1", "rating": 9, "review": "Yes.",
                 "is_loved": True, "created_at": "2026-10-01T00:00:00Z", "review_like_count": 3, "review_reply_count": 0}]
        fake, calls = self._supabase_double({
            "profiles": [{"id": "u1", "username": "maya.listens"}],
            "episode_logs": lambda params: ([{"id": "x"}], {"Content-Range": "0-0/42"}) if params.get("select") == "id" else rows,
            "profile_details": self._denied(),
            "profile_favorites": self._denied(),
            "lists": self._denied(),
            "user_follows": lambda params: ([], {"Content-Range": "*/5" if "following_id" in params else "*/2"}),
        })
        episode = data.Episode(id="2", title="Grass Apes")
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake), \
                mock.patch.object(data, "episode", return_value=episode):
            page = data.profile_page("Maya.Listens")
        self.assertEqual(page.profile.logged_count, 42)
        self.assertIsNone(page.avatar_url)
        self.assertIsNone(page.favorites)
        self.assertIsNone(page.lists)
        self.assertEqual((page.followers, page.following), (5, 2))
        self.assertEqual(len(page.recent_reviews), 1)
        self.assertEqual(page.recent_reviews[0].like_count, 3)
        self.assertEqual(page.recent_reviews[0].episode.title, "Grass Apes")
        self.assertEqual(page.recent_reviews[0].username, "maya.listens")
        # The logged count leaves out bare listen-later saves.
        count_call = next(params for path, params in calls if path == "episode_logs" and params.get("select") == "id")
        self.assertIn("listen_later.is.false", count_call["or"])
        recent_call = next(params for path, params in calls if path == "episode_logs" and params.get("select") != "id")
        self.assertEqual(recent_call["user_id"], "eq.u1")
        self.assertEqual(recent_call["order"], "created_at.desc")

    def test_profile_page_lookup_reads_open_sections(self):
        fake, _ = self._supabase_double({
            "profiles": [{"id": "0b6f1c2e-4a5d-4e8f-9a1b-000000000001", "username": "maya"}],
            "episode_logs": [],
            "profile_details": [{"avatar_path": "0b6f1c2e-4a5d-4e8f-9a1b-000000000001/avatar.jpg",
                                 "avatar_updated_at": "2026-10-01T10:00:00Z"}],
            "profile_favorites": [{"kind": "podcast", "podcast_id": "387129", "episode_id": None},
                                  {"kind": "episode", "podcast_id": "../x", "episode_id": "1"}],
            "lists": [{"id": LIST_ID, "title": " Road trip ", "list_items": [{"count": 9}]}],
            "user_follows": ([], {"Content-Range": "*/0"}),
        })
        self.app.config.update(SONAR_SUPABASE_URL="https://example.supabase.co")
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake), \
                mock.patch.object(data, "podcast", return_value=data.Podcast(id="387129", name="Planet Money")):
            page = data.profile_page("maya")
        self.assertEqual(page.avatar_url, "https://example.supabase.co/storage/v1/object/public/avatars/"
                                          "0b6f1c2e-4a5d-4e8f-9a1b-000000000001/avatar.jpg?v=20261001T100000Z")
        self.assertEqual([item.title for item in page.favorites], ["Planet Money"])
        self.assertEqual([(entry.title, entry.item_count) for entry in page.lists], [("Road trip", 9)])
        self.assertEqual(page.recent_reviews, [])
        # Zero followers and following could be RLS hiding rows: the stats stay hidden.
        self.assertIsNone(page.followers)
        self.assertIsNone(page.following)

    def test_avatar_url_refuses_a_path_outside_the_owner_folder(self):
        fake, _ = self._supabase_double({"profile_details": [{"avatar_path": "someone-else/avatar.jpg"}]})
        self.app.config.update(SONAR_SUPABASE_URL="https://example.supabase.co")
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake):
            self.assertIsNone(data.avatar_url("0b6f1c2e-4a5d-4e8f-9a1b-000000000001"))
            self.assertIsNone(data.avatar_url("not-a-uuid"))

    def test_review_lookups_read_counts_and_more(self):
        row = {"id": LOG_ID, "user_id": USER_ID, "episode_id": "2", "podcast_id": "1", "rating": 0, "review": " Hi ",
               "is_loved": False, "review_like_count": 4, "review_reply_count": None}
        fake, calls = self._supabase_double({
            "episode_logs": [row],
            "profiles": [{"id": USER_ID, "username": "maya"}],
        })
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake), \
                mock.patch.object(data, "episode", return_value=None):
            item = data.review(LOG_ID)
            self.assertEqual((item.username, item.rating, item.text, item.like_count, item.reply_count),
                             ("maya", None, "Hi", 4, None))
            data.more_reviews(item)
        more_call = calls[-1][1]
        self.assertEqual(more_call["id"], f"neq.{LOG_ID}")
        self.assertEqual(more_call["user_id"], f"eq.{USER_ID}")
        self.assertEqual(more_call["limit"], data.MORE_REVIEWS)

    def test_episode_reviews_lookup(self):
        rows = [
            {"id": LOG_ID, "user_id": USER_ID, "episode_id": "2", "podcast_id": "1", "rating": 8, "review": "Great."},
            {"id": "aaaaaaaa-0000-4000-8000-000000000000", "user_id": "5e1f0000-0000-4000-8000-000000000002", "episode_id": "2", "podcast_id": "1",
             "rating": 4, "review": "   "},
        ]
        fake, calls = self._supabase_double({
            "episode_logs": rows,
            "profiles": [{"id": USER_ID, "username": "maya"}],
        })
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake):
            items = data.episode_reviews("2")
            self.assertEqual(data.episode_reviews("2; drop"), [])
        self.assertEqual([(item.username, item.text) for item in items], [("maya", "Great.")])
        self.assertEqual(calls[0][1]["episode_id"], "eq.2")
        self.assertTrue(calls[0][1]["order"].startswith("review_like_count.desc"))

    def test_existing_sonar_pages_unchanged(self):
        for path in ("/sonar", "/sonar/privacy", "/sonar/support"):
            self.assertEqual(self.client.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
