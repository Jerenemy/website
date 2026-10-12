"""Tier 3: creator kit (rating badges, embed snippets, creator pages) and public recap pages."""

import datetime as dt
import html as html_lib
import os
import re
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
import xml.etree.ElementTree as ET
from unittest import mock

from PIL import Image

from app import create_app
from app.blueprints.sonar_share import badge, data, og

SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1"
SVG = "{http://www.w3.org/2000/svg}"
USER_ID = "5e1f0000-0000-4000-8000-000000000001"


class _FakeResponse:
    def __init__(self, rows, headers=None):
        self._rows = rows
        self.headers = headers or {}

    def json(self):
        return self._rows


def _show(pid="387129", name="Planet Money"):
    return data.Podcast(id=pid, name=name, author="NPR", artwork="https://img/pm.jpg")


def _log(day, episode_id, podcast_id="1", rating=None, review=None, loved=False, listen_later=None, listened=None,
         created=None, log_id=None):
    return {
        "id": log_id or f"d351c000-0000-4000-8003-{abs(hash((day, episode_id))) % 10**12:012d}",
        "user_id": USER_ID, "episode_id": episode_id, "podcast_id": podcast_id, "rating": rating, "review": review,
        "is_loved": loved, "listen_later": listen_later, "is_listened": listened, "logged_date": day,
        "created_at": created or (f"{day}T12:00:00+00:00" if day and day[:4].isdigit() and "-" in day else "2025-03-03T12:00:00+00:00"),
    }


class _Base(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "stats.sqlite3")
        self.app.config.update(TESTING=True, SONAR_OG_CACHE_DIR=os.path.join(self.tmp, "og"),
                               SONAR_STATS_DATABASE_PATH=self.db_path)
        self.client = self.app.test_client()
        data._cache.clear()
        og.clear_memory_cache()
        for patcher in (
            mock.patch.object(og, "fetch_artwork", side_effect=lambda url: Image.new("RGB", (600, 600), (200, 60, 50))),
            mock.patch.object(data.requests, "get", side_effect=AssertionError("network")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path, **kwargs):
        return self.client.get(path, headers={"User-Agent": SAFARI}, **kwargs)

    def views(self):
        if not os.path.exists(self.db_path):
            return []
        with closing(sqlite3.connect(self.db_path)) as connection:
            return connection.execute("SELECT kind, source, count FROM sonar_share_views ORDER BY kind, source").fetchall()

    def clicks(self):
        if not os.path.exists(self.db_path):
            return []
        with closing(sqlite3.connect(self.db_path)) as connection:
            return connection.execute(
                "SELECT kind, source, target, count FROM sonar_share_clicks ORDER BY kind, source, target").fetchall()


# --- Badges -------------------------------------------------------------------------------

class BadgeTests(_Base):
    def _parse(self, response):
        root = ET.fromstring(response.data)
        self.assertEqual(root.tag, f"{SVG}svg")
        return root

    def test_podcast_badge_is_valid_svg_with_rating(self):
        with mock.patch.object(data, "podcast_rating", return_value=(4.3, 128)):
            response = self.client.get("/sonar/badge/p/387129.svg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/svg+xml; charset=utf-8")
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=3600")
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
        root = self._parse(response)
        self.assertEqual((root.get("width"), root.get("height")), (str(badge.WIDTH), str(badge.HEIGHT)))
        text = "".join(root.itertext())
        self.assertIn("★ 4.3 · 128 ratings", text)
        self.assertIn("Rated 4.3 out of 5 from 128 ratings on Sonar", root.find(f"{SVG}title").text)
        self.assertNotIn(b"<script", response.data)
        self.assertNotIn(b"href", response.data)

    def test_badge_sizes_are_fixed(self):
        sizes = set()
        for rating in ((4.3, 1), (4.9, 123456), (None, 0)):
            root = ET.fromstring(badge.svg(*badge.rating_text(*rating)))
            sizes.add((root.get("width"), root.get("height"), root.get("viewBox")))
        self.assertEqual(len(sizes), 1)

    def test_no_ratings_variant(self):
        with mock.patch.object(data, "podcast_rating", return_value=(None, 0)):
            root = self._parse(self.client.get("/sonar/badge/p/387129.svg"))
        self.assertIn("Rate it on Sonar", "".join(root.itertext()))
        self.assertNotIn("★", "".join(root.itertext()))

    def test_light_and_dark_themes(self):
        with mock.patch.object(data, "podcast_rating", return_value=(4.3, 128)):
            dark = self.client.get("/sonar/badge/p/387129.svg").get_data(as_text=True)
            light = self.client.get("/sonar/badge/p/387129.svg?theme=light").get_data(as_text=True)
            other = self.client.get("/sonar/badge/p/387129.svg?theme=<x>").get_data(as_text=True)
        self.assertIn(badge.THEMES["dark"]["left"], dark)
        self.assertIn(badge.THEMES["light"]["left"], light)
        self.assertNotIn(badge.THEMES["light"]["left"], dark)
        self.assertEqual(other, dark)  # unknown themes fall back to dark; the value is never echoed
        ET.fromstring(light)

    def test_text_is_escaped(self):
        hostile = '<script>alert("x")</script> & ]]> ★'
        markup = badge.svg("★ " + hostile, hostile, theme="light")
        root = ET.fromstring(markup)  # still well-formed XML
        self.assertNotIn("<script>", markup)
        self.assertIn(hostile, root.find(f"{SVG}title").text)
        self.assertIn(hostile, root.get("aria-label"))

    def test_counts_are_compact(self):
        self.assertEqual(badge.rating_text(4.25, 1)[0], "★ 4.2 · 1 rating")
        self.assertEqual(badge.compact(1234), "1,234")
        self.assertEqual(badge.compact(12345), "12.3k")
        self.assertEqual(badge.compact(120000), "120k")
        self.assertEqual(badge.compact(2_500_000), "2.5M")

    def test_episode_badge(self):
        with mock.patch.object(data, "episode_rating", return_value=(4.8, 23)) as rating:
            root = self._parse(self.client.get("/sonar/badge/e/387129/60827464893.svg?theme=light"))
        rating.assert_called_once_with("60827464893")
        self.assertIn("4.8 · 23 ratings", "".join(root.itertext()))

    def test_failed_lookup_is_a_generic_badge_cached_briefly(self):
        with mock.patch.object(data, "podcast_rating", return_value=None):
            response = self.client.get("/sonar/badge/p/387129.svg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=300")
        self.assertIn("Rate it on Sonar", response.get_data(as_text=True))

    def test_bad_ids_are_404_without_lookups(self):
        with mock.patch.object(data, "podcast_rating") as podcast, mock.patch.object(data, "episode_rating") as episode:
            for path in ("/sonar/badge/p/abc.svg", "/sonar/badge/p/1%3Cx.svg", "/sonar/badge/e/1/x.svg",
                         "/sonar/badge/e/x/1.svg", "/sonar/badge/p/" + "1" * 21 + ".svg"):
                self.assertEqual(self.client.get(path).status_code, 404, path)
            podcast.assert_not_called()
            episode.assert_not_called()

    def test_badge_fetches_are_not_page_views(self):
        with mock.patch.object(data, "podcast_rating", return_value=(4.3, 128)):
            self.get("/sonar/badge/p/387129.svg")
            self.get("/sonar/badge/p/387129.svg?s=creator")
        self.assertEqual(self.views(), [])

    def test_conditional_requests(self):
        with mock.patch.object(data, "podcast_rating", return_value=(4.3, 128)):
            first = self.client.get("/sonar/badge/p/387129.svg")
            again = self.client.get("/sonar/badge/p/387129.svg", headers={"If-None-Match": first.headers["ETag"]})
        self.assertEqual(again.status_code, 304)

    def test_podcast_rating_lookup(self):
        calls = []

        def fake(path, params, headers=None):
            calls.append((path, params, headers))
            return _FakeResponse([{"rating": 8}, {"rating": 9}, {"rating": 0}, {"rating": None}],
                                 {"Content-Range": "0-3/7"})

        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake):
            self.assertEqual(data.podcast_rating("387129"), (4.2, 7))
            self.assertEqual(data.podcast_rating("387129"), (4.2, 7))  # cached
            self.assertIsNone(data.podcast_rating("x")[0])
        self.assertEqual(len(calls), 1)
        path, params, headers = calls[0]
        self.assertEqual((path, params["podcast_id"], params["rating"]), ("episode_logs", "eq.387129", "gt.0"))
        self.assertLessEqual(params["limit"], data.CREATOR_MAX_ROWS)
        self.assertEqual(headers, {"Prefer": "count=exact"})

    def test_podcast_rating_failure_is_none(self):
        with self.app.app_context(), \
                mock.patch.object(data, "_supabase", side_effect=data.requests.ConnectionError("down")):
            self.assertIsNone(data.podcast_rating("387129"))


# --- Creator pages ------------------------------------------------------------------------

def _creator_stats():
    episode = data.Episode(id="101", title="Tariffs & <you>", artwork="https://img/e.jpg", podcast=_show())
    review = data.Review(id="d351c000-0000-4000-8003-000000000001", username="maya.listens", rating=10,
                         is_loved=True, text="Best <b>explainer</b>.", episode=episode, episode_id="101")
    return data.CreatorStats(
        podcast_id="387129", logs=312, ratings=128, average=4.3, reviews=57,
        top_episodes=[data.EpisodeStat("101", 4.8, 23, episode), data.EpisodeStat("102", 4.5, 4, None)],
        top_reviews=[review],
    )


class CreatorTests(_Base):
    def _page(self, path="/sonar/creators/p/387129", stats=None, rating=(4.3, 128)):
        with mock.patch.object(data, "podcast", return_value=_show()), \
                mock.patch.object(data, "creator_stats", return_value=stats or _creator_stats()), \
                mock.patch.object(data, "podcast_rating", return_value=rating):
            return self.get(path)

    def test_creator_page_shows_stats_badge_and_snippets(self):
        response = self._page()
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Planet Money", page)
        self.assertIn("312", page)
        self.assertIn("<strong>4.3</strong> · 128 ratings", page)
        self.assertIn("57", page)
        self.assertIn('src="/sonar/badge/p/387129.svg"', page)
        self.assertIn('src="/sonar/badge/p/387129.svg?theme=light"', page)
        # Escaped user content: the episode title and review never become markup.
        self.assertIn("Tariffs &amp; &lt;you&gt;", page)
        self.assertNotIn("<b>explainer</b>", page)
        snippet = html_lib.unescape(re.search(r'<code id="snip-dark-html">(.*?)</code>', page, re.S).group(1))
        self.assertEqual(
            snippet,
            '<a href="http://localhost/sonar/p/387129?s=creator"><img src="http://localhost/sonar/badge/p/387129.svg" '
            'alt="Planet Money on Sonar" width="230" height="28"></a>',
        )
        markdown = html_lib.unescape(re.search(r'<code id="snip-light-markdown">(.*?)</code>', page, re.S).group(1))
        self.assertEqual(markdown, "[![Planet Money on Sonar](http://localhost/sonar/badge/p/387129.svg?theme=light)]"
                                   "(http://localhost/sonar/p/387129?s=creator)")
        link = html_lib.unescape(re.search(r'<code id="snip-dark-link">(.*?)</code>', page, re.S).group(1))
        self.assertEqual(link, "http://localhost/sonar/p/387129?s=creator")
        # The snippet itself parses as the HTML a podcaster would paste.
        self.assertTrue(snippet.startswith("<a href=") and snippet.endswith("</a>"))

    def test_each_episode_row_offers_its_own_badge(self):
        page = self._page().get_data(as_text=True)
        buttons = re.findall(r'data-dark="([^"]+)" data-light="([^"]+)"', page)
        self.assertEqual(len(buttons), 2)
        dark, light = (html_lib.unescape(value) for value in buttons[0])
        self.assertIn('href="http://localhost/sonar/e/387129/101?s=creator"', dark)
        self.assertIn('src="http://localhost/sonar/badge/e/387129/101.svg"', dark)
        self.assertIn('alt="Tariffs &amp; &lt;you&gt; on Sonar"', dark)  # escaped inside the snippet too
        self.assertIn("101.svg?theme=light", light)

    def test_creator_page_without_ratings_or_stats(self):
        response = self._page(stats=data.CreatorStats(podcast_id="387129"), rating=(None, 0))
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("No ratings on Sonar yet", page)
        with mock.patch.object(data, "podcast", return_value=_show()), \
                mock.patch.object(data, "creator_stats", return_value=None), \
                mock.patch.object(data, "podcast_rating", return_value=None):
            self.assertEqual(self.get("/sonar/creators/p/387129").status_code, 200)

    def test_unknown_or_malformed_show_is_404(self):
        with mock.patch.object(data, "podcast", return_value=None):
            self.assertEqual(self.get("/sonar/creators/p/387129").status_code, 404)
        self.assertEqual(self.get("/sonar/creators/p/abc").status_code, 404)
        self.assertEqual(self.views(), [])

    def test_creator_views_and_taps_are_counted_as_creator(self):
        page = self._page().get_data(as_text=True)
        self._page("/sonar/creators/p/387129?s=creator")
        self.assertEqual(self.views(), [("creator", "creator", 1), ("creator", "unknown", 1)])
        open_href = html_lib.unescape(re.search(r'<a class="button button--primary" href="([^"]+)">Open in Sonar', page).group(1))
        response = self.get(open_href)
        self.assertEqual(response.headers["Location"], "sonar://podcast/387129")
        self.assertEqual(self.clicks(), [("creator", "creator", "app", 1)])

    def test_badge_click_through_counts_as_a_creator_sourced_view(self):
        with mock.patch.object(data, "podcast", return_value=_show()):
            self.get("/sonar/p/387129?s=creator")
        self.assertEqual(self.views(), [("podcast", "creator", 1)])

    def test_creator_og_image(self):
        with mock.patch.object(data, "podcast", return_value=_show()), \
                mock.patch.object(data, "podcast_rating", return_value=(4.3, 128)):
            response = self.client.get("/sonar/og/creator/p/387129.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(Image.open(__import__("io").BytesIO(response.data)).size, (og.W, og.H))
        self.assertEqual(self.client.get("/sonar/og/creator/p/x.png").status_code, 404)
        page = self._page().get_data(as_text=True)
        self.assertIn('property="og:image" content="http://localhost/sonar/og/creator/p/387129.png"', page)

    def test_creator_pages_are_not_app_links(self):
        response = self.client.get("/.well-known/apple-app-site-association")
        paths = {c["/"] for c in response.get_json()["applinks"]["details"][0]["components"]}
        self.assertFalse(any(p.startswith(("/sonar/creators", "/sonar/badge")) for p in paths))


class CreatorLandingTests(_Base):
    def test_landing_page(self):
        response = self.get("/sonar/creators")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Find your show", page)
        self.assertIn('name="q"', page)
        self.assertEqual(page.count("<svg xmlns"), 3)  # the example badges, inline
        self.assertEqual(self.views(), [("creator", "unknown", 1)])

    def test_query_resolves_ids_and_links_to_the_creator_page(self):
        cases = {
            "387129": "387129",
            " 387129 ": "387129",
            "https://jeremyzay.com/sonar/p/387129?s=podcast": "387129",
            "jeremyzay.com/sonar/e/387129/60827464893": "387129",
            "/sonar/creators/p/42": "42",
            "sonar://podcast/387129": "387129",
        }
        for query, podcast_id in cases.items():
            response = self.get("/sonar/creators", query_string={"q": query})
            self.assertEqual(response.status_code, 303, query)
            self.assertEqual(response.headers["Location"], f"/sonar/creators/p/{podcast_id}", query)

    def test_apple_podcasts_links_resolve_through_podcast_index(self):
        with mock.patch.object(data, "podcast_id_from_apple", return_value="152249") as lookup:
            response = self.get("/sonar/creators", query_string={
                "q": "https://podcasts.apple.com/us/podcast/radiolab/id152249110?i=1000"})
        lookup.assert_called_once_with("152249110")
        self.assertEqual(response.headers["Location"], "/sonar/creators/p/152249")
        with mock.patch.object(data, "podcast_id_from_apple", return_value=None):
            response = self.get("/sonar/creators", query_string={"q": "https://podcasts.apple.com/podcast/id1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("couldn&#39;t match that Apple Podcasts link", response.get_data(as_text=True))

    def test_other_urls_are_never_fetched_or_followed(self):
        with mock.patch.object(data, "search_podcasts", return_value=[]) as search:
            for query in ("https://evil.example/sonar/p/1", "//evil.example", "javascript:alert(1)"):
                response = self.get("/sonar/creators", query_string={"q": query})
                self.assertEqual(response.status_code, 200, query)
                self.assertNotIn("Location", response.headers)
        self.assertEqual(search.call_count, 3)

    def test_name_search(self):
        shows = [_show(), _show("42", "Planet <Money> Jr")]
        with mock.patch.object(data, "search_podcasts", return_value=shows):
            page = self.get("/sonar/creators", query_string={"q": "planet money"}).get_data(as_text=True)
        self.assertIn('href="/sonar/creators/p/42"', page)
        self.assertIn("Planet &lt;Money&gt; Jr", page)
        self.assertIn('name="robots" content="noindex"', page)
        with mock.patch.object(data, "search_podcasts", return_value=None):
            page = self.get("/sonar/creators", query_string={"q": "planet"}).get_data(as_text=True)
        self.assertIn("Search isn", page)
        with mock.patch.object(data, "search_podcasts", return_value=[]):
            page = self.get("/sonar/creators", query_string={"q": "zzz"}).get_data(as_text=True)
        self.assertIn("No shows found", page)

    def test_search_and_apple_lookups(self):
        calls = []

        def fake(path, params):
            calls.append((path, params))
            if path == "podcasts/byitunesid":
                return {"feed": {"id": 152249, "title": "Radiolab"}}
            return {"feeds": [{"id": 1, "title": " A ", "author": "B", "artwork": "https://a"},
                              {"id": "x", "title": "bad id"}, {"id": 2}]}

        with self.app.app_context(), mock.patch.object(data, "_podcast_index", side_effect=fake):
            self.assertEqual(data.podcast_id_from_apple("152249110"), "152249")
            shows = data.search_podcasts("  radio   lab ")
            self.assertEqual([(s.id, s.name) for s in shows], [("1", "A")])
            self.assertEqual(data.search_podcasts(""), [])
        self.assertEqual(calls[1], ("search/byterm", {"q": "radio lab", "max": data.SEARCH_RESULTS}))


class CreatorStatsTests(_Base):
    def test_summarize_show(self):
        rows = [
            {"episode_id": "1", "rating": 10, "review": "great"},
            {"episode_id": "1", "rating": 8, "review": ""},
            {"episode_id": "2", "rating": 10, "review": None},  # one rating: doesn't rank
            {"episode_id": "3", "rating": 6, "review": "ok"},
            {"episode_id": "3", "rating": 7, "review": None},
            {"episode_id": "4", "rating": None, "review": "words only"},
            {"episode_id": "5", "rating": 11},  # out of range
        ]
        ratings, average, reviews, top = data.summarize_show(rows)
        self.assertEqual(ratings, 5)
        self.assertEqual(average, round((10 + 8 + 10 + 6 + 7) / 5 / 2, 1))
        self.assertEqual(reviews, 3)
        self.assertEqual([(s.episode_id, s.average, s.count) for s in top], [("1", 4.5, 2), ("3", 3.2, 2)])
        # With no episode rated twice, single ratings rank.
        _, _, _, top = data.summarize_show([{"episode_id": "9", "rating": 4}, {"episode_id": "8", "rating": 6}])
        self.assertEqual([s.episode_id for s in top], ["8", "9"])

    def test_creator_stats_queries_are_bounded(self):
        calls = []

        def fake(path, params, headers=None):
            calls.append(params)
            if "or" in params:
                return _FakeResponse([{"episode_id": "1", "rating": 8, "review": "x"}], {"Content-Range": "0-0/40"})
            return _FakeResponse([{"id": "d351c000-0000-4000-8003-000000000001", "user_id": USER_ID, "episode_id": "1",
                                   "podcast_id": "387129", "rating": 8, "review": "Nice", "is_loved": False}])

        with self.app.app_context(), mock.patch.object(data, "_supabase", side_effect=fake), \
                mock.patch.object(data, "_usernames", return_value={USER_ID: "maya"}), \
                mock.patch.object(data, "episode", return_value=None):
            stats = data.creator_stats("387129")
        self.assertEqual((stats.logs, stats.ratings, stats.reviews, stats.sampled), (40, 1, 1, True))
        self.assertEqual([r.username for r in stats.top_reviews], ["maya"])
        self.assertTrue(all(params["podcast_id"] == "eq.387129" and params["limit"] <= data.CREATOR_MAX_ROWS
                            for params in calls))
        self.assertEqual(calls[0]["or"], data.LOGGED_FILTER)


# --- Recaps -------------------------------------------------------------------------------

TODAY = dt.date(2026, 10, 11)


class PeriodTests(unittest.TestCase):
    def test_valid_periods(self):
        year = data.parse_period("2025", TODAY)
        self.assertEqual((year.start, year.end, year.label, year.noun), (dt.date(2025, 1, 1), dt.date(2026, 1, 1), "2025", "year"))
        month = data.parse_period("2025-12", TODAY)
        self.assertEqual((month.start, month.end, month.label), (dt.date(2025, 12, 1), dt.date(2026, 1, 1), "December 2025"))
        self.assertIsNotNone(data.parse_period("2024-01", TODAY))
        self.assertIsNotNone(data.parse_period("2026-10", TODAY))  # the running month
        self.assertIsNotNone(data.parse_period("2026", TODAY))
        self.assertIsNotNone(data.parse_period("2026-11", dt.date(2026, 10, 31)))  # a day ahead of UTC is fine

    def test_invalid_periods(self):
        for value in ("2023", "2023-12", "2026-11", "2027", "2025-13", "2025-00", "2025-1", "25", "2025-01-01",
                      "abcd", "", None, "2025\n", " 2025", "２０２５"):
            self.assertIsNone(data.parse_period(value, TODAY), repr(value))


class RecapMathTests(unittest.TestCase):
    def test_aggregation(self):
        period = data.parse_period("2025-03", TODAY)
        rows = [
            _log("2025-03-01", "10", "1", rating=8, review="Good"),
            _log("2025-03-02", "11", "1", rating=10, loved=True),
            _log("2025-03-03", "12", "2", rating=6, review="  "),
            _log("2025-03-03", "13", "1", loved=True, listened=True),
            _log("2025-03-03", "10", "1", rating=4),          # relisten: counts once, its day still counts
            _log("2025-03-10", "14", "2", review="Words"),
            _log("2025-03-11", "15", "3", listen_later=True),  # a bare listen-later save: not logged
            _log("2025-02-28", "16", "1", rating=10),         # outside the period
            _log("2025-04-01", "17", "1", rating=10),         # outside the period
            _log("3/20/25", "18", "3", rating=9, created="2025-05-01T00:00:00Z"),  # legacy short date
            _log(None, "19", "3", created="2025-03-21T23:00:00+00:00"),            # no logged_date: created_at
            _log("2025-01-15", "20", "1", rating=10, created="2025-03-05T00:00:00Z"),  # backdated out of March
        ]
        recap = data.summarize_recap(rows, period, "maya")
        self.assertEqual(recap.episodes, 7)  # 10, 11, 12, 13, 14, 18, 19
        self.assertEqual(recap.reviews, 2)   # "Good", "Words" ("  " is not a review)
        self.assertEqual(recap.loved, 2)
        self.assertEqual(recap.ratings, 4)   # 8, 10, 6, 9
        self.assertEqual(recap.average, round((8 + 10 + 6 + 9) / 4 / 2, 1))
        self.assertEqual(recap.days, 6)      # March 1, 2, 3, 10, 20, 21 (the listen-later save on the 11th is not a log)
        self.assertEqual(recap.longest_streak, 3)  # March 1-3
        self.assertEqual([(t.podcast_id, t.count) for t in recap.top_podcasts], [("1", 3), ("2", 2), ("3", 2)])
        self.assertEqual(recap.best.episode_id, "11")  # 10/10 and loved
        self.assertTrue(recap.best.is_loved)
        self.assertFalse(recap.empty)

    def test_streak_across_a_month_boundary_in_a_year(self):
        period = data.parse_period("2025", TODAY)
        rows = [_log(day, str(i)) for i, day in enumerate(("2025-01-30", "2025-01-31", "2025-02-01", "2025-02-03"))]
        recap = data.summarize_recap(rows, period)
        self.assertEqual((recap.longest_streak, recap.days, recap.episodes), (3, 4, 4))
        self.assertIsNone(recap.best)
        self.assertIsNone(recap.average)

    def test_empty(self):
        recap = data.summarize_recap([], data.parse_period("2025", TODAY), "maya")
        self.assertTrue(recap.empty)
        self.assertEqual((recap.longest_streak, recap.top_podcasts), (0, []))

    def test_log_day(self):
        self.assertEqual(data.log_day({"logged_date": "2025-03-01"}), dt.date(2025, 3, 1))
        self.assertEqual(data.log_day({"logged_date": "2025-03-01T10:00:00Z"}), dt.date(2025, 3, 1))
        self.assertEqual(data.log_day({"logged_date": "3/1/25"}), dt.date(2025, 3, 1))
        self.assertEqual(data.log_day({"logged_date": "01.03.25"}), dt.date(2025, 3, 1))
        self.assertEqual(data.log_day({"logged_date": "Mar 1, 2025", "created_at": "2025-04-02T00:00:00Z"}),
                         dt.date(2025, 4, 2))
        self.assertIsNone(data.log_day({"logged_date": "13/40/25"}))


class RecapLookupTests(_Base):
    def test_recap_query(self):
        calls = []

        def fake(path, params, headers=None):
            calls.append((path, params))
            return _FakeResponse([_log("2025-03-01", "10", "1", rating=8)])

        period = data.parse_period("2025-03", TODAY)
        with self.app.app_context(), \
                mock.patch.object(data, "profile", return_value=data.Profile(username="maya", id=USER_ID)), \
                mock.patch.object(data, "_supabase", side_effect=fake), \
                mock.patch.object(data, "podcast", return_value=_show("1")), \
                mock.patch.object(data, "episode", return_value=None), \
                mock.patch.object(data, "avatar_url", return_value=None):
            recap = data.recap("maya", period)
        self.assertEqual(recap.episodes, 1)
        self.assertEqual(recap.top_podcasts[0].podcast.name, "Planet Money")
        path, params = calls[0]
        self.assertEqual(path, "episode_logs")
        self.assertEqual(params["user_id"], f"eq.{USER_ID}")
        self.assertIn("logged_date.gte.2025-03-01", params["or"])
        self.assertIn("created_at.lt.2025-04-01", params["or"])
        self.assertLessEqual(params["limit"], data.RECAP_MAX_ROWS)

    def test_unknown_user_is_none(self):
        with self.app.app_context(), mock.patch.object(data, "profile", return_value=None):
            self.assertIsNone(data.recap("nobody", data.parse_period("2025", TODAY)))


def _recap(period="2025", **changes):
    parsed = data.parse_period(period)
    values = dict(username="maya.listens", period=parsed, episodes=128, reviews=23, loved=12, ratings=97, average=4.1,
                  days=74, longest_streak=9,
                  top_podcasts=[data.TopPodcast("387129", 31, _show()), data.TopPodcast("42", 3, None)])
    values.update(changes)
    item = data.Recap(**values)
    if "best" not in changes and item.episodes:
        item.best = data.Review(id="d351c000-0000-4000-8003-000000000000", username="maya.listens", rating=10,
                                is_loved=True, text="<i>Wow</i>", episode=data.Episode(id="2", title="Colors", podcast=_show()))
    return item


class RecapPageTests(_Base):
    def test_recap_page(self):
        with mock.patch.object(data, "recap", return_value=_recap()):
            response = self.get("/sonar/u/maya.listens/recap/2025?s=recap")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>@maya.listens&#39;s 2025 on Sonar · Sonar</title>", page)
        self.assertIn("128", page)
        self.assertIn("episodes logged", page)
        self.assertIn("9</strong><span>day streak", page)
        self.assertIn("Planet Money", page)
        self.assertIn('href="/sonar/p/387129"', page)
        self.assertIn("Colors", page)
        self.assertIn("&lt;i&gt;Wow&lt;/i&gt;", page)
        self.assertIn('content="http://localhost/sonar/og/u/maya.listens/recap/2025.png"', page)
        self.assertIn('rel="canonical" href="http://localhost/sonar/u/maya.listens/recap/2025"', page)
        self.assertNotIn('name="robots"', page)
        self.assertEqual(self.views(), [("recap", "recap", 1)])
        # Open in Sonar goes through /sonar/go, which rebuilds the recap app link.
        href = html_lib.unescape(re.search(r'<a class="button button--primary" href="([^"]+)">Open in Sonar', page).group(1))
        self.assertIn("u=/sonar/u/maya.listens/recap/2025", href)
        go = self.get(href)
        self.assertEqual(go.status_code, 302)
        self.assertEqual(go.headers["Location"], "sonar://recap/maya.listens/2025")
        store = html_lib.unescape(re.search(r'href="([^"]+)">Get Sonar on the App Store', page).group(1))
        self.get(store)
        self.assertEqual(self.clicks(), [("recap", "recap", "app", 1), ("recap", "recap", "appstore", 1)])

    def test_month_recap(self):
        with mock.patch.object(data, "recap", return_value=_recap("2025-10")) as lookup:
            page = self.get("/sonar/u/maya.listens/recap/2025-10").get_data(as_text=True)
        self.assertEqual(lookup.call_args[0][1].key, "2025-10")
        self.assertIn("October 2025", page)
        self.assertIn("month in podcasts", page)

    def test_empty_period_is_friendly(self):
        empty = _recap(episodes=0, reviews=0, loved=0, ratings=0, average=None, days=0, longest_streak=0, top_podcasts=[])
        with mock.patch.object(data, "recap", return_value=empty):
            response = self.get("/sonar/u/maya.listens/recap/2025")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nothing logged yet", page)
        self.assertIn('name="robots" content="noindex"', page)
        self.assertIn("Open in Sonar", page)

    def test_invalid_periods_and_names_are_404(self):
        with mock.patch.object(data, "recap") as lookup:
            for path in ("/sonar/u/maya/recap/2023", "/sonar/u/maya/recap/2025-13", "/sonar/u/maya/recap/2999",
                         "/sonar/u/maya/recap/25", "/sonar/u/maya/recap/2025-1", "/sonar/u/maya/recap/latest",
                         "/sonar/u/bad%20name!/recap/2025", "/sonar/og/u/maya/recap/2023.png",
                         "/sonar/og/u/bad%20name!/recap/2025.png"):
                self.assertEqual(self.get(path).status_code, 404, path)
            lookup.assert_not_called()
        self.assertEqual(self.views(), [])

    def test_unknown_user_is_404_but_offers_the_app(self):
        with mock.patch.object(data, "recap", return_value=None):
            response = self.get("/sonar/u/nobody/recap/2025")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Open in Sonar", response.get_data(as_text=True))

    def test_recap_og_image(self):
        with mock.patch.object(data, "recap", return_value=_recap()):
            response = self.client.get("/sonar/og/u/maya.listens/recap/2025.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertIn("max-age=86400", response.headers["Cache-Control"])  # a finished year keeps
        import io
        self.assertEqual(Image.open(io.BytesIO(response.data)).size, (og.W, og.H))

    def test_running_period_og_image_is_cached_briefly(self):
        this_month = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
        with mock.patch.object(data, "recap", return_value=_recap(this_month)):
            response = self.client.get(f"/sonar/og/u/maya.listens/recap/{this_month}.png")
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=300")
        empty = _recap(episodes=0, top_podcasts=[])
        with mock.patch.object(data, "recap", return_value=empty):
            self.assertEqual(self.client.get("/sonar/og/u/maya.listens/recap/2024-02.png").status_code, 200)

    def test_recap_path_is_covered_by_the_profile_app_link(self):
        response = self.client.get("/.well-known/apple-app-site-association")
        paths = {c["/"] for c in response.get_json()["applinks"]["details"][0]["components"]}
        self.assertIn("/sonar/u/*", paths)


class GoTests(_Base):
    def test_go_accepts_recap_paths(self):
        from app.blueprints.sonar_share.routes import share_target
        self.assertEqual(share_target("/sonar/u/maya.listens/recap/2025"), ("recap", "sonar://recap/maya.listens/2025"))
        self.assertEqual(share_target("/sonar/u/maya/recap/2025-03"), ("recap", "sonar://recap/maya/2025-03"))
        for path in ("/sonar/u/maya/recap/", "/sonar/u/maya/recap/2025-3", "/sonar/u/maya/recap/2025/x",
                     "/sonar/u/maya/recap/2025\n", "/sonar/u/maya/recap/2025?x", "/sonar/u/ma ya/recap/2025",
                     "/sonar/u/maya/recap/2025-03-01", "https://evil.example/sonar/u/maya/recap/2025"):
            self.assertIsNone(share_target(path), repr(path))

    def test_go_still_rejects_open_redirects(self):
        for u in ("https://evil.example/sonar/u/maya/recap/2025", "//evil.example/sonar/u/maya/recap/2025",
                  "/sonar/u/maya/recap/2025/../../evil", "/sonar/creators/p/1", "/sonar/badge/p/1.svg",
                  "sonar://recap/maya/2025"):
            response = self.get("/sonar/go", query_string={"to": "app", "k": "creator", "u": u})
            self.assertEqual(response.status_code, 400, u)
            self.assertNotIn("Location", response.headers)

    def test_go_kinds(self):
        self.get("/sonar/go", query_string={"to": "app", "k": "review", "s": "creator", "u": "/sonar/u/maya/recap/2025"})
        self.get("/sonar/go", query_string={"to": "app", "k": "creator", "s": "creator", "u": "/sonar/e/1/2"})
        self.get("/sonar/go", query_string={"to": "appstore", "k": "creator", "s": "creator"})
        self.get("/sonar/go", query_string={"to": "appstore", "k": "recap", "s": "recap"})
        self.assertEqual(self.clicks(), [
            ("creator", "creator", "app", 1),     # a creator page's tap keeps the page's kind
            ("creator", "creator", "appstore", 1),
            ("recap", "creator", "app", 1),       # otherwise the kind comes from the validated path
            ("recap", "recap", "appstore", 1),
        ])


if __name__ == "__main__":
    unittest.main()
