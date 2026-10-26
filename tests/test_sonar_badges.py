"""Badges and photos for the people on Sonar's share pages: every badge under a profile's
name, one beside a name everywhere else, and each person's own photo."""

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
MAYA = "5e1f0000-0000-4000-8000-000000000001"
SAM = "5e1f0000-0000-4000-8000-000000000002"
PHOTO = "https://example.supabase.co/storage/v1/object/public/avatars/{}/avatar.jpg?v=1"


class _FakeResponse:
    def __init__(self, rows, headers=None):
        self._rows = rows
        self.headers = headers or {}

    def json(self):
        return self._rows


def _page(**changes):
    values = dict(profile=data.Profile(username="maya.listens", logged_count=12, id=MAYA),
                  followers=3, following=4, favorites=[], recent_reviews=[], lists=[])
    values.update(changes)
    return data.ProfilePage(**values)


def _review(**changes):
    show = data.Podcast(id="1", name="Radiolab")
    values = dict(id=LOG_ID, username="maya.listens", rating=9, is_loved=False, text="Loved it.",
                  episode=data.Episode(id="2", title="Grass Apes", podcast=show), user_id=MAYA)
    values.update(changes)
    return data.Review(**values)


def _badge_line(html):
    match = re.search(r'<ul class="badges">(.*?)</ul>', html, re.S)
    return match.group(1) if match else None


class BadgePageTests(unittest.TestCase):
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
        patcher = mock.patch.object(og, "fetch_artwork", side_effect=lambda url: Image.new("RGB", (600, 600)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def get(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def test_profile_lists_every_badge_under_the_name_in_the_apps_order(self):
        with mock.patch.object(data, "profile_page", return_value=_page(badges=["founder", "tester", "early_adopter"])):
            html = self.get("/sonar/u/maya.listens")
        line = _badge_line(html)
        self.assertIsNotNone(line)
        titles = re.findall(r"</svg>([^<]+)</li>", line)
        self.assertEqual(titles, ["Founder", "Tester", "Early adopter"])
        self.assertIn('title="Built Sonar."', line)
        self.assertEqual(line.count('class="badge-glyph"'), 3)
        # The line sits under the name, before the numbers.
        self.assertLess(html.index("<h1"), html.index('<ul class="badges">'))
        self.assertLess(html.index('<ul class="badges">'), html.index('<ul class="stats">'))

    def test_a_creator_with_known_shows_says_what_they_make(self):
        shows = [data.Podcast(id="152249", name="Radiolab"), data.Podcast(id="42", name="Hard Fork")]
        page = _page(badges=["creator", "early_adopter"], creator_shows=shows)
        with mock.patch.object(data, "profile_page", return_value=page):
            html = self.get("/sonar/u/maya.listens")
        self.assertNotIn(">Creator</li>", html)
        self.assertIn(">Early adopter</li>", html)
        self.assertIn('href="/sonar/p/152249"', html)
        self.assertIn("Makes <strong>Radiolab</strong>", html)
        self.assertIn("Makes <strong>Hard Fork</strong>", html)

    def test_a_creator_without_known_shows_keeps_the_label(self):
        with mock.patch.object(data, "profile_page", return_value=_page(badges=["creator"])):
            html = self.get("/sonar/u/maya.listens")
        self.assertIn(">Creator</li>", html)
        self.assertNotIn('<ul class="badges badges--shows">', html)

    def test_no_badges_no_line(self):
        with mock.patch.object(data, "profile_page", return_value=_page()):
            html = self.get("/sonar/u/maya.listens")
        self.assertNotIn('<ul class="badges', html)
        self.assertNotIn('class="badge-glyph"', html)

    def test_review_byline_has_the_authors_photo_and_badge(self):
        review = _review(avatar_url=PHOTO.format(MAYA), badge="core_designer")
        with mock.patch.object(data, "review", return_value=review), \
                mock.patch.object(data, "more_reviews", return_value=[]):
            html = self.get(f"/sonar/r/{LOG_ID}")
        byline = re.search(r'<div class="byline">(.*?)</div>', html, re.S).group(1)
        self.assertIn(f'src="{PHOTO.format(MAYA)}"', byline)
        self.assertIn('aria-label="Core Designer"', byline)
        self.assertLess(byline.index("@maya.listens"), byline.index('class="name-badge"'))

    def test_review_byline_without_photo_or_badge_is_the_monogram(self):
        with mock.patch.object(data, "review", return_value=_review()), \
                mock.patch.object(data, "more_reviews", return_value=[]):
            html = self.get(f"/sonar/r/{LOG_ID}")
        byline = re.search(r'<div class="byline">(.*?)</div>', html, re.S).group(1)
        self.assertIn(">M</span>", byline)
        self.assertNotIn("name-badge", byline)

    def test_episode_reviewers_have_their_photos_and_badges(self):
        reviewers = [
            _review(user_id=SAM, username="sam", avatar_url=PHOTO.format(SAM), badge="creator"),
            _review(id="aaaaaaaa-0000-4000-8000-000000000000", username="maya.listens"),
        ]
        with mock.patch.object(data, "episode", return_value=data.Episode(id="2", title="Grass Apes")), \
                mock.patch.object(data, "community_rating", return_value=(4.2, 3)), \
                mock.patch.object(data, "episode_reviews", return_value=reviewers):
            html = self.get("/sonar/e/1/2")
        self.assertIn(f'src="{PHOTO.format(SAM)}"', html)
        self.assertIn('@sam<span class="name-badge" title="Creator">', html)
        self.assertEqual(html.count('class="name-badge"'), 1)

    def test_list_owner_invite_and_recap_show_the_name_badge(self):
        sonar_list = data.SonarList(id=LIST_ID, title="Road trip", username="maya.listens", user_id=MAYA,
                                    avatar_url=PHOTO.format(MAYA), badge="founder")
        with mock.patch.object(data, "sonar_list", return_value=sonar_list):
            html = self.get(f"/sonar/l/{LIST_ID}")
        self.assertIn(f'src="{PHOTO.format(MAYA)}"', html)
        self.assertIn('</strong><span class="name-badge" title="Founder">', html)

        with mock.patch.object(data, "profile_page", return_value=_page(badges=["founder", "early_adopter"])):
            html = self.get("/sonar/i/maya.listens")
        self.assertIn('<h1>@maya.listens<span class="name-badge" title="Founder">', html)
        self.assertNotIn('<ul class="badges">', html)  # the full line is the profile's

        recap = data.Recap(username="maya.listens", period=data.parse_period("2025"), episodes=3, badge="creator")
        with mock.patch.object(data, "recap", return_value=recap):
            html = self.get("/sonar/u/maya.listens/recap/2025")
        self.assertIn('</strong><span class="name-badge" title="Creator">', html)

    def test_every_badge_has_a_glyph_title_and_meaning(self):
        for kind in data.BADGE_KINDS:
            with mock.patch.object(data, "profile_page", return_value=_page(badges=[kind])):
                html = self.get("/sonar/u/maya.listens")
            line = _badge_line(html)
            self.assertIn(f">{data.BADGE_TITLES[kind]}</li>", line, kind)
            self.assertIn(f'title="{data.BADGE_EXPLANATIONS[kind]}"'.replace("'", "&#39;"), line, kind)
            self.assertRegex(line, r'<svg class="badge-glyph" viewBox="[^"]+" aria-hidden="true"><(path|rect) ', kind)


class BadgeLookupTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SONAR_SUPABASE_URL="https://example.supabase.co")
        data._cache.clear()

    def _supabase(self, tables):
        calls = []

        def fake(path, params, headers=None):
            calls.append((path, params))
            value = tables.get(path, [])
            if isinstance(value, Exception):
                raise value
            return _FakeResponse(value)

        return fake, calls

    def _denied(self):
        return data.requests.HTTPError("401 permission denied", response=mock.MagicMock(status_code=401))

    def test_name_badge_is_founder_then_core_designer_then_creator(self):
        self.assertEqual(data.name_badge(["early_adopter", "creator", "founder"]), "founder")
        self.assertEqual(data.name_badge(["creator", "core_designer"]), "core_designer")
        self.assertEqual(data.name_badge(["creator"]), "creator")
        self.assertIsNone(data.name_badge(["tester", "early_adopter"]))
        self.assertIsNone(data.name_badge(None))

    def test_badges_reads_one_batch_and_keeps_the_apps_order(self):
        fake, calls = self._supabase({"profile_badges": [
            {"user_id": MAYA, "kind": "early_adopter"},
            {"user_id": MAYA, "kind": "founder"},
            {"user_id": MAYA, "kind": "superstar"},          # a kind this site doesn't know
            {"user_id": SAM, "kind": "creator"},
            {"user_id": "someone-else", "kind": "founder"},  # not asked for
        ]})
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake):
            found = data.badges([SAM, MAYA, MAYA, "not-a-uuid", None])
        self.assertEqual(found, {MAYA: ["founder", "early_adopter"], SAM: ["creator"]})
        self.assertEqual(len(calls), 1)
        path, params = calls[0]
        self.assertEqual(path, "profile_badges")
        self.assertEqual(params["select"], "user_id,kind")  # the columns anon may read
        self.assertEqual(params["user_id"], f"in.({MAYA},{SAM})")

    def test_badges_unreadable_is_nobody_has_any(self):
        fake, _ = self._supabase({"profile_badges": self._denied()})
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake):
            self.assertEqual(data.badges([MAYA]), {})
            self.assertEqual(data.badges([]), {})

    def test_avatar_urls_checks_each_owner_folder(self):
        fake, calls = self._supabase({"profile_details": [
            {"user_id": MAYA, "avatar_path": f"{MAYA}/avatar.jpg", "avatar_updated_at": "2026-10-01T10:00:00Z"},
            {"user_id": SAM, "avatar_path": f"{MAYA}/avatar.jpg"},  # someone else's photo: refused
        ]})
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake):
            photos = data.avatar_urls([MAYA, SAM])
        self.assertEqual(photos, {MAYA: "https://example.supabase.co/storage/v1/object/public/avatars/"
                                        f"{MAYA}/avatar.jpg?v=20261001T100000Z"})
        self.assertEqual(calls[0][1]["select"], "user_id,avatar_path,avatar_updated_at")

    def test_episode_reviews_come_with_photos_and_name_badges(self):
        rows = [
            {"id": LOG_ID, "user_id": MAYA, "episode_id": "2", "podcast_id": "1", "rating": 8, "review": "Great."},
            {"id": "aaaaaaaa-0000-4000-8000-000000000000", "user_id": SAM, "episode_id": "2", "podcast_id": "1",
             "rating": 6, "review": "Fine."},
        ]
        fake, calls = self._supabase({
            "episode_logs": rows,
            "profiles": [{"id": MAYA, "username": "maya"}, {"id": SAM, "username": "sam"}],
            "profile_details": [{"user_id": SAM, "avatar_path": f"{SAM}/avatar.jpg"}],
            "profile_badges": [{"user_id": MAYA, "kind": "founder"}, {"user_id": SAM, "kind": "early_adopter"}],
        })
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake):
            items = data.episode_reviews("2")
        self.assertEqual([(item.username, item.badge) for item in items], [("maya", "founder"), ("sam", None)])
        self.assertEqual([bool(item.avatar_url) for item in items], [False, True])
        self.assertEqual(sum(1 for path, _ in calls if path == "profile_badges"), 1)
        self.assertEqual(sum(1 for path, _ in calls if path == "profile_details"), 1)

    def test_profile_page_reads_badges_and_a_creators_shows(self):
        fake, calls = self._supabase({
            "profiles": [{"id": MAYA, "username": "maya"}],
            "profile_badges": [{"user_id": MAYA, "kind": "creator"}, {"user_id": MAYA, "kind": "early_adopter"}],
            "creator_shows": [{"podcast_id": "152249"}, {"podcast_id": "../x"}],
        })
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake), \
                mock.patch.object(data, "podcast", side_effect=lambda pid: data.Podcast(id=pid, name="Radiolab")):
            page = data.profile_page("maya")
        self.assertEqual(page.badges, ["creator", "early_adopter"])
        self.assertEqual(page.name_badge, "creator")
        self.assertEqual([(show.id, show.name) for show in page.creator_shows], [("152249", "Radiolab")])
        shows_call = next(params for path, params in calls if path == "creator_shows")
        self.assertEqual(shows_call["user_id"], f"eq.{MAYA}")
        self.assertEqual(shows_call["order"], "verified_at.asc")

    def test_profile_page_skips_creator_shows_for_everyone_else(self):
        fake, calls = self._supabase({
            "profiles": [{"id": MAYA, "username": "maya"}],
            "profile_badges": [{"user_id": MAYA, "kind": "founder"}],
        })
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake):
            page = data.profile_page("maya")
        self.assertEqual(page.badges, ["founder"])
        self.assertEqual(page.creator_shows, [])
        self.assertNotIn("creator_shows", [path for path, _ in calls])

    def test_list_and_review_lookups_fill_in_the_person(self):
        fake, _ = self._supabase({
            "lists": [{"id": LIST_ID, "user_id": MAYA, "title": "Road trip"}],
            "profiles": [{"id": MAYA, "username": "maya"}],
            "list_items": [],
            "episode_logs": [{"id": LOG_ID, "user_id": MAYA, "episode_id": "2", "podcast_id": "1", "rating": 8}],
            "profile_details": [{"user_id": MAYA, "avatar_path": f"{MAYA}/avatar.jpg"}],
            "profile_badges": [{"user_id": MAYA, "kind": "core_designer"}],
        })
        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake), \
                mock.patch.object(data, "episode", return_value=None):
            sonar_list = data.sonar_list(LIST_ID)
            review = data.review(LOG_ID)
        for person in (sonar_list, review):
            self.assertEqual(person.badge, "core_designer")
            self.assertTrue(person.avatar_url.endswith(f"/avatars/{MAYA}/avatar.jpg"))


if __name__ == "__main__":
    unittest.main()
