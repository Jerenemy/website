import json
import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from app import create_app
from app.portfolio.store import KINDS, PortfolioStore

ROOT = Path(__file__).resolve().parents[1]
SHIPPED_PORTFOLIO = ROOT / "app" / "data" / "portfolio.json"
HOME_STATIC = ROOT / "app" / "static" / "home"
SITE_STATIC = ROOT / "app" / "static" / "site"


class Page(HTMLParser):
    """The bits of a rendered page these tests read: rail anchors, the scene's JSON, forms."""

    def __init__(self):
        super().__init__()
        self.rail, self.links, self.forms, self.fields, self.scripts, self.preloads = [], [], [], [], [], []
        self.metas, self.properties, self.site_data, self.importmap = {}, {}, None, None
        self.head_scripts = []
        self._in_rail = self._in_links = False
        self._script = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "ol" and a.get("id") == "rail":
            self._in_rail = True
        elif tag == "ul" and a.get("id") == "links":
            self._in_links = True
        elif tag == "a" and self._in_rail and "data-index" in a:
            self.rail.append(a)
        elif tag == "a" and self._in_links:
            self.links.append(a)
        elif tag == "form":
            self.forms.append(a)
        elif tag in ("input", "textarea"):
            self.fields.append(a)
        elif tag == "meta" and "name" in a:
            self.metas[a["name"]] = a.get("content")
        elif tag == "meta" and "property" in a:
            self.properties[a["property"]] = a.get("content")
        elif tag == "link" and a.get("rel") == "modulepreload":
            self.preloads.append(a["href"])
        elif tag == "script":
            self.scripts.append(a)
            self._script = a

    def handle_endtag(self, tag):
        if tag == "ol":
            self._in_rail = False
        elif tag == "ul":
            self._in_links = False
        elif tag == "script":
            self._script = None

    def handle_data(self, data):
        if self._script is None:
            return
        if self._script.get("id") == "site-data":
            self.site_data = json.loads(data)
        elif self._script.get("type") == "importmap":
            self.importmap = json.loads(data)
        elif not self._script:
            self.head_scripts.append(data)


def parse(html: str) -> Page:
    page = Page()
    page.feed(html)
    return page


class EditForm(HTMLParser):
    """The admin form's fields as a browser would submit them untouched (file inputs empty)."""

    def __init__(self):
        super().__init__()
        self.data, self._textarea, self._select = {}, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("name") and a.get("type") != "file":
            if a.get("type") != "checkbox":
                self.data[a["name"]] = a.get("value") or ""
            elif "checked" in a:
                self.data[a["name"]] = "on"
        elif tag == "textarea":
            self._textarea = a["name"]
            self.data[self._textarea] = ""
            self.set_cdata_mode("textarea")   # its content is text (the descriptions hold links)
        elif tag == "select":
            self._select = a["name"]
        elif tag == "option" and self._select and "selected" in a:
            self.data[self._select] = a.get("value") or ""

    def handle_endtag(self, tag):
        if tag == "textarea":
            self._textarea = None
            self.clear_cdata_mode()
        elif tag == "select":
            self._select = None

    def handle_data(self, data):
        if self._textarea:
            self.data[self._textarea] += data


class HomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.portfolio = Path(self.temp.name) / "portfolio.json"
        shutil.copy(SHIPPED_PORTFOLIO, self.portfolio)
        self.settings = Path(self.temp.name) / "site_settings.json"
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-only",
                               PORTFOLIO_DATA_PATH=str(self.portfolio), SITE_SETTINGS_PATH=str(self.settings))
        self.client = self.app.test_client()

    def published(self):
        return PortfolioStore(str(self.portfolio)).list_items()

    def test_home_renders_every_published_work_in_rail_order(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        page = parse(response.text)
        works = self.published()
        self.assertGreaterEqual(len(works), 9)
        self.assertEqual([a["data-id"] for a in page.rail], [w["id"] for w in works])
        self.assertEqual([a["data-index"] for a in page.rail], [str(i) for i in range(len(works))])
        self.assertEqual([a["href"] for a in page.rail], [w["href"] for w in works])
        self.assertEqual(page.rail[0].get("aria-current"), "true")
        self.assertTrue(all("aria-current" not in a for a in page.rail[1:]))
        # The scene's data is valid JSON and names the same works, in the same order.
        self.assertIsNotNone(page.site_data)
        self.assertEqual([w["id"] for w in page.site_data["works"]], [w["id"] for w in works])
        for sent, item in zip(page.site_data["works"], works):
            self.assertEqual(sent, {k: item[k] for k in ("id", "title", "kind", "line", "href")})
            self.assertIn(sent["kind"], KINDS)
            self.assertTrue(sent["line"])
        self.assertEqual(page.site_data["person"]["name"], "Jeremy Zay")
        self.assertEqual([l["href"] for l in page.site_data["person"]["links"]],
                         ["/resume", "/blog", "https://github.com/Jerenemy", "https://www.linkedin.com/in/jeremy-zay/", "/contact"])
        self.assertEqual([a["href"] for a in page.links], [l["href"] for l in page.site_data["person"]["links"]])

    def test_home_markup_is_the_contract_the_scene_adopts(self):
        html = self.client.get("/").text
        page = parse(html)
        self.assertIn("<title>Jeremy Zay</title>", html)
        self.assertIn('<span class="sr">Posters, Research, </span><span class="line">Generative models that design molecules for mutant p53</span>', html)
        self.assertIn(f'<span class="no">01 / {len(self.published()):02d}</span><span class="title">Posters</span>', html)
        self.assertIn('aria-label="Jeremy Zay, home"', html)
        for element_id in ("stage", "masthead", "rail", "caption", "head", "cap-a", "cap-b", "detail", "cap-kind",
                           "cap-line", "cap-open", "announce", "cap-hint", "links", "leader", "dock", "tag", "tag-no", "tag-title"):
            self.assertIn(f'id="{element_id}"', html, element_id)
        self.assertEqual(page.importmap, {"imports": {"three": "/static/home/vendor/three-r186/three.module.min.js"}})
        self.assertIn({"type": "module", "src": "/static/home/src/main.js"}, page.scripts)
        # Every module is preloaded (the bundle, then main.js first), except the test hook probe.js.
        modules = sorted(p.name for p in (HOME_STATIC / "src").glob("*.js") if p.name != "probe.js")
        self.assertEqual(page.preloads[:2], ["/static/home/vendor/three-r186/three.module.min.js", "/static/home/src/main.js"])
        self.assertEqual(sorted(page.preloads[1:]), [f"/static/home/src/{m}" for m in modules])
        self.assertNotIn("/static/home/src/probe.js", html)
        # No HTML comment reaches the visitor (the template's notes are Jinja comments).
        self.assertNotIn("<!--", html)
        self.assertIn('href="/static/home/styles.css"', html)
        # The old homepage is gone from it.
        for old in ("ambient-fluid", "glightbox", "webgl-fluid", "site-header", "project-card"):
            self.assertNotIn(old, html)

    def test_meta_description_is_home_description_without_html(self):
        self.settings.write_text(json.dumps({"home_description": "I study <a href='/x'>p53</a> &amp; diffusion."}))
        page = parse(self.client.get("/").text)
        self.assertEqual(page.metas["description"], "I study p53 & diffusion.")

    def test_head_script_guards_the_scene_and_old_links(self):
        page = parse(self.client.get("/").text)
        head = "\n".join(page.head_scripts)
        # An old /#contact link goes to the contact page.
        self.assertIn("location.hash === '#contact'", head)
        self.assertIn('location.replace("/contact")', head)
        # The scene's layout is taken only where import maps work, and withdrawn on any error
        # before the scene has registered (the list is then the page).
        self.assertIn("supports('importmap')", head)
        self.assertIn("addEventListener('error'", head)
        self.assertIn("if (!window.__demo) root.classList.remove('gl')", head)

    def test_link_previews_show_the_homepage(self):
        for path in ("/", "/contact"):
            with self.subTest(path=path):
                page = parse(self.client.get(path + "?n=3").text)
                self.assertEqual(page.properties["og:image"], "http://localhost/static/img/brand/tribar-preview.jpg")
                self.assertEqual((page.properties["og:image:width"], page.properties["og:image:height"]), ("1200", "630"))
                self.assertNotIn("fluid", page.properties["og:image:alt"])
                self.assertEqual(page.metas["twitter:card"], "summary_large_image")
                self.assertEqual(page.properties["og:url"], "http://localhost" + path)   # no query string
        from PIL import Image
        with Image.open(ROOT / "app" / "static" / "img" / "brand" / "tribar-preview.jpg") as image:
            self.assertEqual((image.format, image.size), ("JPEG", (1200, 630)))

    def test_unpublished_and_legacy_items(self):
        data = json.loads(self.portfolio.read_text())
        data["items"][1]["is_published"] = False
        # Saved before kind/line/href existed: the image is its destination, as on the old cards.
        for key in ("kind", "line", "href"):
            data["items"][0].pop(key)
        # Nowhere to go at all: left off the loop rather than linked to nothing.
        data["items"][2].update(href="", image_full="")
        self.portfolio.write_text(json.dumps(data))
        page = parse(self.client.get("/").text)
        ids = [a["data-id"] for a in page.rail]
        self.assertNotIn(data["items"][1]["id"], ids)
        self.assertNotIn(data["items"][2]["id"], ids)
        published = [i for i in json.loads(SHIPPED_PORTFOLIO.read_text())["items"] if i["is_published"]]
        self.assertEqual(len(ids), len([i for i in published if i["id"] not in (data["items"][1]["id"], data["items"][2]["id"])]))
        self.assertEqual(page.rail[0]["href"], "/static/" + data["items"][0]["image_full"])
        self.assertEqual(page.site_data["works"][0]["kind"], "")
        self.assertEqual([w["id"] for w in page.site_data["works"]], ids)

    def test_every_local_href_resolves(self):
        adapter = self.app.url_map.bind("localhost")
        slugs = {p.stem for p in Path(self.app.config["BLOG_POSTS_DIR"]).glob("*.md")}
        hrefs = [w["href"] for w in self.published()] + ["/resume", "/blog", "/contact"]
        for href in hrefs:
            if href.startswith("https://"):
                continue
            with self.subTest(href=href):
                endpoint, args = adapter.match(href)
                if endpoint == "public.blog_post":
                    self.assertIn(args["slug"], slugs)
                if not href.startswith("/ear/"):   # /ear/ is its own service behind nginx
                    response = self.client.get(href)
                    response.close()
                    self.assertEqual(response.status_code, 200)

    def test_posters_page_shows_every_poster(self):
        """The two research posters are one work: one page with both, newest first, each with its PDF."""
        for path in ("/posters", "/posters/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        html = self.client.get("/posters").text
        self.assertLess(html.index('id="diffusion"'), html.index('id="reinforcement-learning"'))
        for pdf in ("/poster-diffusion-2025", "/poster-rl-2024"):
            self.assertIn(f'href="{pdf}"', html)
            self.assertEqual(self.client.get(pdf).status_code, 200, pdf)
            # Each poster is drawn from its PDF file (static/site/pdf-figure.js), its image standing in.
            self.assertIn(f'data-pdf="/static/files{pdf}.pdf"', html)
            self.assertEqual(self.client.get(f"/static/files{pdf}.pdf").status_code, 200, pdf)
        self.assertIn('src="/static/site/pdf-figure.js"', html)

    def test_contact_page_renders_the_form(self):
        for path in ("/contact", "/contact/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        page = parse(response.text)
        self.assertEqual([{k: f.get(k) for k in ("id", "method", "action")} for f in page.forms],
                         [{"id": "contact-form", "method": "post", "action": "/api/contact"}])
        self.assertEqual([(f.get("name"), "required" in f) for f in page.fields],
                         [("name", True), ("email", True), ("message", True), ("website", False)])
        self.assertIn({"src": "/static/js/contact.js", "defer": None}, page.scripts)
        self.assertIn('id="contact-status"', response.text)
        # The contact page is built on the design system (templates/layout.html), like every page.
        self.assertIn('href="/static/site/tokens.css"', response.text)
        self.assertIn('href="/static/site/site.css"', response.text)
        self.assertNotIn("<canvas", response.text)
        self.assertIn('href="/contact" rel="noopener" aria-label="Contact" aria-current="page"', response.text)
        self.assertNotIn("<!--", response.text)

    def test_contact_form_works_without_javascript(self):
        from unittest import mock
        self.app.config.update(MAIL_SERVER="127.0.0.1", MAIL_USERNAME="qa@localhost", MAIL_DEFAULT_SENDER="qa@localhost")
        fields = {"name": "Ada", "email": "ada@example.com", "message": "Hello"}
        with mock.patch("app.blueprints.api.routes.mail.send") as send:
            # The browser posts the form itself: the answer is the contact page, with the outcome.
            response = self.client.post("/api/contact", data=fields)
            self.assertEqual((response.status_code, response.headers["Location"]), (303, "/contact?status=sent"))
            self.assertEqual(send.call_count, 1)
            self.assertIn("From: Ada <ada@example.com>", send.call_args[0][0].body)
            page = self.client.get("/contact?status=sent").text
            self.assertIn('aria-live="polite">Message sent successfully!</p>', page)
            response = self.client.post("/api/contact", data={**fields, "message": ""})
            self.assertEqual((response.status_code, response.headers["Location"]), (303, "/contact?status=missing"))
            # A bot fills the hidden field: told it went, nothing is sent.
            response = self.client.post("/api/contact", data={**fields, "website": "http://spam.example"})
            self.assertEqual((response.status_code, response.headers["Location"]), (303, "/contact?status=sent"))
            self.assertEqual(send.call_count, 1)
            # The JSON API (static/js/contact.js and the other pages) answers as before.
            response = self.client.post("/api/contact", json={**fields, "website": ""})
            self.assertEqual((response.status_code, response.get_json()), (200, {"ok": True}))
            response = self.client.post("/api/contact", json={"name": "Ada"})
            self.assertEqual((response.status_code, response.get_json()), (400, {"error": "Missing fields"}))
            self.assertEqual(send.call_count, 2)
            send.side_effect = RuntimeError("smtp down")
            with self.assertLogs(self.app.logger, "ERROR"):
                response = self.client.post("/api/contact", data=fields)
            self.assertEqual(response.headers["Location"], "/contact?status=failed")
            self.assertIn("Failed to send message", self.client.get(response.headers["Location"]).text)
        self.assertEqual(self.client.get("/contact?status=<b>").text.count("<b>"), 0)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "portfolio.json"

    def test_legacy_item_without_new_fields_loads(self):
        self.path.write_text(json.dumps({"items": [{
            "id": "old", "title": "Old", "short_desc": "s", "long_desc": "l", "image_full": "img/a.png",
            "image_thumb": "img/a.png", "image_alt": "a", "sort_order": 0, "is_published": True,
        }, {"id": "odd", "title": "Odd", "kind": "Sculpture", "sort_order": 1}]}))
        store = PortfolioStore(str(self.path))
        old, odd = store.list_items()
        self.assertEqual((old["kind"], old["line"], old["href"]), ("", "", ""))
        self.assertEqual(old["short_desc"], "s")
        self.assertEqual(odd["kind"], "")   # unknown kinds are not passed on
        updated = store.update_item("old", {"title": "Old"})
        self.assertEqual((updated["kind"], updated["line"], updated["href"]), ("", "", ""))

    def test_create_gives_a_readable_unique_id(self):
        store = PortfolioStore(str(self.path))
        first = store.create_item({"title": "Curve Explorer", "kind": "engineering", "line": "l", "href": "/x"})
        second = store.create_item({"title": "Curve Explorer!", "kind": "nonsense"})
        third = store.create_item({"title": "???"})
        self.assertEqual(first["id"], "curve-explorer")
        self.assertEqual(second["id"], "curve-explorer-2")
        self.assertEqual(second["kind"], "")
        self.assertRegex(third["id"], r"^[0-9a-f]{32}$")
        self.assertEqual((first["kind"], first["line"], first["href"]), ("engineering", "l", "/x"))


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.portfolio = Path(self.temp.name) / "portfolio.json"
        shutil.copy(SHIPPED_PORTFOLIO, self.portfolio)
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-only", PORTFOLIO_DATA_PATH=str(self.portfolio),
                               SITE_SETTINGS_PATH=str(Path(self.temp.name) / "site_settings.json"),
                               UPLOADS_DIR=str(Path(self.temp.name) / "uploads"),
                               UPLOADS_THUMBS_DIR=str(Path(self.temp.name) / "uploads" / "thumbs"))
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["csrf_token"] = "token"
        self.store = PortfolioStore(str(self.portfolio))

    def post(self, path, **fields):
        form = {"csrf_token": "token", "title": "Tribar", "kind": "engineering",
                "line": "  A Penrose tribar  you can walk ", "href": "/blog/tribar", "sort_order": "10",
                "is_published": "on", "auto_thumbnail": "on"}
        form.update(fields)
        return self.client.post(path, data=form)

    def test_form_offers_the_new_fields(self):
        html = self.client.get("/admin/portfolio/new").text
        for kind in KINDS:
            self.assertIn(f'<option value="{kind}">', html)
        self.assertIn('name="line"', html)
        self.assertIn('name="href"', html)
        html = self.client.get("/admin/portfolio/zaybot/edit").text
        self.assertIn('<option value="engineering" selected>', html)
        self.assertIn('value="An AlphaZero-style chess engine"', html)
        self.assertIn('value="/blog/zaybot"', html)

    def test_create_and_update_persist_kind_line_href(self):
        response = self.post("/admin/portfolio/new")
        self.assertEqual(response.status_code, 302)
        item = self.store.get_item("tribar")
        self.assertIsNotNone(item)
        self.assertEqual((item["kind"], item["line"], item["href"]), ("engineering", "A Penrose tribar you can walk", "/blog/tribar"))
        self.assertEqual(item["image_full"], "")
        # The homepage picks the eleventh work up with no code change.
        page = parse(self.client.get("/").text)
        self.assertEqual(len(page.rail), len(PortfolioStore(str(SHIPPED_PORTFOLIO)).list_items()) + 1)
        self.assertEqual(page.rail[-1]["data-id"], "tribar")
        self.assertEqual(page.site_data["works"][-1]["line"], "A Penrose tribar you can walk")

        response = self.post("/admin/portfolio/tribar/edit", kind="play", line="Still a tribar", href="https://example.com/tribar")
        self.assertEqual(response.status_code, 302)
        item = self.store.get_item("tribar")
        self.assertEqual((item["kind"], item["line"], item["href"]), ("play", "Still a tribar", "https://example.com/tribar"))

    def test_invalid_kind_line_and_href_are_rejected(self):
        before = self.portfolio.read_text()
        cases = [
            {"kind": "sculpture"}, {"kind": ""}, {"line": ""}, {"line": "x" * 73}, {"line": "<b>bold</b>"},
            {"href": ""}, {"href": "blog/tribar"}, {"href": "//evil.example"}, {"href": "javascript:alert(1)"},
            {"href": "/a b"}, {"href": "ftp://example.com"}, {"title": ""}, {"title": "x" * 25},
        ]
        for fields in cases:
            with self.subTest(fields=fields):
                response = self.post("/admin/portfolio/new", **fields)
                self.assertEqual(response.status_code, 200)
                self.assertIn("admin-form", response.text)
                self.assertEqual(self.portfolio.read_text(), before)
                response = self.post("/admin/portfolio/zaybot/edit", **fields)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.portfolio.read_text(), before)

    def test_every_shipped_item_saves_unchanged_through_the_edit_form(self):
        # What an admin sends by opening an item and pressing Save: each shipped work must pass
        # validation as it stands (KArchive's image is an SVG already in /static).
        for item in self.store.list_items(include_unpublished=True):
            with self.subTest(item=item["id"]):
                form = EditForm()
                form.feed(self.client.get(f"/admin/portfolio/{item['id']}/edit").text)
                response = self.client.post(f"/admin/portfolio/{item['id']}/edit", data=form.data)
                self.assertEqual(response.status_code, 302, response.text[:400] if response.status_code != 302 else "")
                saved = self.store.get_item(item["id"])
                for key in ("title", "kind", "line", "href", "short_desc", "long_desc", "image_full", "image_thumb",
                            "image_alt", "sort_order", "is_published"):
                    self.assertEqual(saved[key], item[key], key)

    def test_title_is_at_most_24_characters(self):
        html = self.client.get("/admin/portfolio/new").text
        self.assertIn('id="title" name="title" value="" maxlength="24" required', html)
        response = self.post("/admin/portfolio/new", title="Twenty-four characters!!")
        self.assertEqual(response.status_code, 302)
        response = self.post("/admin/portfolio/new", title="Twenty-five characters!!!")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Title must be at most 24 characters.", response.text)

    def test_alt_text_is_required_only_with_an_image(self):
        before = self.portfolio.read_text()
        response = self.post("/admin/portfolio/new", image_full="img/projects/zaychess-full.png",
                             image_thumb="img/projects/zaychess-thumb.png", image_alt="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("alt text is required", response.text)
        self.assertEqual(self.portfolio.read_text(), before)


class ShippedAssetsTests(unittest.TestCase):
    """What the homepage loads exists, and git will carry it to the server (the repository's
    .gitignore is an allowlist: a file without its own entry silently never deploys)."""

    def needed(self):
        files = [HOME_STATIC / "styles.css", SITE_STATIC / "tokens.css", SITE_STATIC / "site.css", SITE_STATIC / "site.js",
                 HOME_STATIC / "vendor" / "three-r186" / "three.module.min.js"]
        files += sorted((HOME_STATIC / "src").glob("*.js"))
        files += sorted((SITE_STATIC / "themes").glob("*.css")) + sorted((SITE_STATIC / "works").glob("*.css"))
        files += [SITE_STATIC / "pdf-figure.js"]
        pdfjs = ROOT / "app" / "static" / "vendor" / "pdfjs-6.4.299"
        files += [pdfjs / "pdf.min.js", pdfjs / "pdf.worker.min.js"] + sorted((pdfjs / "standard_fonts").glob("*"))
        return files

    def test_scene_modules_resolve(self):
        sources = sorted((HOME_STATIC / "src").glob("*.js"))
        self.assertIn(HOME_STATIC / "src" / "main.js", sources)
        for source in sources:
            for target in re.findall(r"^import [^;]*? from '(\./[^']+)';", source.read_text(), flags=re.M):
                with self.subTest(module=source.name, target=target):
                    self.assertTrue((source.parent / target).is_file())
        bundle = (HOME_STATIC / "vendor" / "three-r186" / "three.module.min.js").read_text()
        self.assertIn("SPDX-License-Identifier: MIT", bundle)
        self.assertNotIn("three.core.js", bundle)   # one file: the core is inlined

    @unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "needs a git checkout")
    def test_homepage_files_are_not_git_ignored(self):
        paths = [str(p.relative_to(ROOT)) for p in self.needed()]
        paths += ["app/templates/home.html", "app/templates/contact.html", "app/templates/_preview_meta.html",
                  "app/templates/layout.html", "app/templates/_ui.html", "app/templates/_theme.html", "app/design.py",
                  "app/static/img/brand/tribar-preview.jpg", "tests/test_home.py"]
        # The design record and the proofs that guard the paradox rule (design/homepage-demo).
        demo = "design/homepage-demo/"
        paths += [demo + name for name in ("CONCEPT.md", "INTEGRATION.md", "index.html", "data.js", "package.json",
                                           "src", "styles.css", "vendor", "site")]
        paths += [str(p.relative_to(ROOT)) for p in sorted((ROOT / demo / "tools").glob("*"))]
        result = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--no-index", *paths],
                                capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "", "ignored by .gitignore: " + result.stdout)


if __name__ == "__main__":
    unittest.main()
