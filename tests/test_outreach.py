import re
import tempfile
import unittest
from unittest import mock

from app import create_app
from app.blueprints.jobbot import JobBotError

LEADS = (
    "name,company,email,company_url,hook,variant,greeting,nudges,replied_after,status,"
    "first_contacted,last_activity,thread_id,notes,follow_up_on\n"
    "Ada Test,Acme AI,ada@acme.test,https://acme.test,A tagline.,quote,yes,vision,nudge1,"
    "meeting-requested,2026-10-01,2026-10-09,abc123,secret note,\n"
    "Bo Test,Beta Labs,bo@beta.test,,Another line.,glaze,no,,,sent,2026-11-01,2026-11-01,def456,,\n"
    "Cy Test,Gamma,cy@gamma.test,,x,question,yes,,,bounced,2026-11-02,2026-11-02,,,\n"
)
STATS = {
    "generated_on": "2026-11-10", "mature_days": 14, "min_mature": 20,
    "hooks": {h: {"sent": 1, "mature": 1, "replies": int(h == "quote"), "positive": 0, "meetings": 0,
                  "rate": float(h == "quote")} for h in ("quote", "glaze", "question")},
    "greetings": {g: {"sent": 1, "mature": 0, "replies": 0, "positive": 0, "meetings": 0, "rate": None} for g in ("yes", "no")},
    "cells": {}, "history": {}, "nudges": [{"nudge": 1, "type": "vision", "sent": 1, "replies": 1, "rate": 1.0}],
    "replied_to_first": 0, "p_best": None,
    "next_run": {"leads": 15, "hooks": {"quote": 5, "glaze": 5, "question": 5}, "greeting_yes": 8,
                 "greeting_no": 7, "why": "equal split until every hook has 20 matured sends"},
}
SEED = [{"id": "s1", "title": "Send me your resume", "context": "quote hook", "ceo_message": "Send your resume.", "reply": "", "why": ""}]


class OutreachCase(unittest.TestCase):
    """The app on a scratch data folder, with the admin login and the routine's sync."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-only", OUTREACH_SYNC_TOKEN="sync-secret",
                               OUTREACH_DATA_DIR=self.tmp.name)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def sync(self, body, token="sync-secret"):
        return self.client.post("/admin/outreach/sync", json=body, headers={"Authorization": f"Bearer {token}"})

    def login(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["csrf_token"] = "csrf"


class OutreachTests(OutreachCase):
    def test_pages_need_the_admin_login(self):
        for path in ("/admin/outreach", "/admin/outreach/ab", "/admin/outreach/voice"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/admin/login", response.headers["Location"])

    def test_sync_needs_the_token(self):
        self.assertEqual(self.sync({"leads_csv": LEADS}, token="wrong").status_code, 404)
        self.app.config["OUTREACH_SYNC_TOKEN"] = None
        self.assertEqual(self.sync({"leads_csv": LEADS}, token="").status_code, 404)

    def test_sync_rejects_a_file_that_is_not_the_leads(self):
        self.assertEqual(self.sync({"leads_csv": "a,b\n1,2\n"}).status_code, 400)

    def test_sync_stores_the_data_and_seeds_the_examples_once(self):
        response = self.sync({"leads_csv": LEADS, "stats": STATS, "seed_examples": SEED})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e["id"] for e in response.json["examples"]], ["s1"])
        # a second seed is ignored, a new real example is added once
        new = {"id": "r1", "ceo_message": "Text me", "reply": "I'll text you now."}
        again = self.sync({"seed_examples": [{"id": "s2", "ceo_message": "x"}], "new_examples": [new, new]})
        self.assertEqual([e["id"] for e in again.json["examples"]], ["s1", "r1"])
        self.assertEqual(again.json["examples"][1]["source"], "real")

    def test_emails_dashboard_lists_replies_first_and_keeps_notes_off_the_page(self):
        self.sync({"leads_csv": LEADS, "stats": STATS})
        self.login()
        page = self.client.get("/admin/outreach").get_data(as_text=True)
        self.assertLess(page.index("Ada Test"), page.index("Bo Test"))
        self.assertIn("mail.google.com/mail/u/jzay@wesleyan.edu/#all/abc123", page)
        self.assertNotIn("secret note", page)
        self.assertIn("50.0%", page)  # 1 reply of the 2 that went out; the bounce does not count
        replied = self.client.get("/admin/outreach?show=replied").get_data(as_text=True)
        self.assertIn("Ada Test", replied)
        self.assertNotIn("Bo Test", replied)

    def test_ab_dashboard_shows_the_split_and_rates(self):
        self.login()
        self.assertIn("Nothing synced yet", self.client.get("/admin/outreach/ab").get_data(as_text=True))
        self.sync({"stats": STATS})
        page = self.client.get("/admin/outreach/ab").get_data(as_text=True)
        self.assertIn("100.0%", page)
        self.assertIn("Equal split", page)

    def test_voice_examples_can_be_answered_added_and_deleted(self):
        self.sync({"seed_examples": SEED})
        self.login()
        self.assertEqual(self.client.post("/admin/outreach/voice/s1", data={"csrf_token": "bad", "reply": "x"}).status_code, 302)
        self.assertEqual(self.sync({}).json["examples"][0]["reply"], "")  # bad CSRF changed nothing

        self.client.post("/admin/outreach/voice/s1", data={
            "csrf_token": "csrf", "title": "Send me your resume", "context": "quote hook",
            "ceo_message": "Send your resume.", "reply": "Here it is: jeremyzay.com/resume", "why": ""})
        self.client.post("/admin/outreach/voice", data={"csrf_token": "csrf", "title": "New", "ceo_message": "Hi?"})
        examples = self.sync({}).json["examples"]
        self.assertEqual(examples[0]["reply"], "Here it is: jeremyzay.com/resume")
        self.assertEqual(len(examples), 2)

        page = self.client.get("/admin/outreach/voice").get_data(as_text=True)
        self.assertLess(page.index("Needs your reply"), page.index('value="New"'))
        self.assertLess(page.index("Answered"), page.index("Here it is"))

        self.client.post(f"/admin/outreach/voice/{examples[1]['id']}/delete", data={"csrf_token": "csrf"})
        self.assertEqual([e["id"] for e in self.sync({}).json["examples"]], ["s1"])


class FakeResponse:
    def __init__(self, payload=None, content=b""):
        self.payload, self.content = payload, content

    def json(self):
        return self.payload


class OutreachResumeTests(OutreachCase):
    """The Resume tab: the thread goes to the job bot's API, the PDF comes back through here."""

    def setUp(self):
        super().setUp()
        self.calls = []
        self.replies = {}
        patcher = mock.patch("app.blueprints.outreach._api", side_effect=self.fake_api)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_api(self, method, path, payload=None, timeout=15):
        self.calls.append((method, path, payload))
        reply = self.replies.get((method, path))
        if isinstance(reply, Exception):
            raise reply
        return reply

    def test_the_tab_needs_the_admin_login(self):
        for path in ("/admin/outreach/resume", "/admin/outreach/resume/abc", "/admin/outreach/resume/abc/pdf"):
            self.assertEqual(self.client.get(path).status_code, 302, path)
        self.assertEqual(self.calls, [])

    def test_making_one_sends_the_thread_and_follows_it(self):
        self.login()
        self.replies[("POST", "/api/reader-resumes")] = FakeResponse({"id": "20261112-1", "status": "running"})
        response = self.client.post("/admin/outreach/resume", data={
            "csrf_token": "csrf", "company": "Satlyt", "thread": "Send me your resume. -Rama"})
        self.assertEqual(response.headers["Location"], "/admin/outreach/resume/20261112-1")
        self.assertEqual(self.calls[-1], ("POST", "/api/reader-resumes",
                                          {"thread": "Send me your resume. -Rama", "company": "Satlyt"}))

        self.replies[("GET", "/api/reader-resumes/20261112-1")] = FakeResponse(
            {"id": "20261112-1", "company": "Satlyt", "status": "running"})
        page = self.client.get("/admin/outreach/resume/20261112-1").get_data(as_text=True)
        self.assertIn('http-equiv="refresh"', page)

        self.replies[("GET", "/api/reader-resumes/20261112-1")] = FakeResponse({
            "id": "20261112-1", "company": "Satlyt", "status": "done", "reading": "On-device ML.",
            "experience": [{"title": "Founder, Thaw", "why": "ships"}], "projects": [{"title": "Sonar", "why": ""}],
            "skills": ["C++"], "refused": []})
        page = self.client.get("/admin/outreach/resume/20261112-1").get_data(as_text=True)
        self.assertNotIn('http-equiv="refresh"', page)
        self.assertIn("/admin/outreach/resume/20261112-1/pdf", page)
        self.assertIn("Founder, Thaw", page)

        self.replies[("GET", "/api/reader-resumes/20261112-1/pdf")] = FakeResponse(content=b"%PDF-1.7")
        pdf = self.client.get("/admin/outreach/resume/20261112-1/pdf")
        self.assertEqual(pdf.data, b"%PDF-1.7")
        self.assertEqual(pdf.headers["Content-Type"], "application/pdf")
        self.assertIn('attachment; filename="Jeremy Zay Resume.pdf"', pdf.headers["Content-Disposition"])

    def test_a_bad_csrf_or_an_empty_form_sends_nothing(self):
        self.login()
        self.client.post("/admin/outreach/resume", data={"csrf_token": "bad", "thread": "x"})
        self.client.post("/admin/outreach/resume", data={"csrf_token": "csrf", "thread": " "})
        self.assertEqual([c for c in self.calls if c[0] == "POST"], [])

    def test_the_list_and_a_bot_that_is_down(self):
        self.sync({"leads_csv": LEADS})
        self.login()
        self.replies[("GET", "/api/reader-resumes")] = FakeResponse({"resumes": [
            {"id": "r1", "company": "Satlyt", "status": "done", "created_at": "2026-11-12T05:00:00+00:00"}]})
        page = self.client.get("/admin/outreach/resume?company=Acme%20AI").get_data(as_text=True)
        self.assertIn("/admin/outreach/resume/r1/pdf", page)
        self.assertIn('value="Acme AI"', page)  # the replied lead's company, from the Emails tab's link
        self.assertIn('<option value="Acme AI">', page)

        self.replies[("GET", "/api/reader-resumes")] = JobBotError(503, "The job bot is not reachable.")
        self.assertIn("not reachable", self.client.get("/admin/outreach/resume").get_data(as_text=True))
        self.replies[("GET", "/api/reader-resumes/r9/pdf")] = JobBotError(404, "not ready")
        self.assertEqual(self.client.get("/admin/outreach/resume/r9/pdf").status_code, 404)
        self.assertEqual(self.client.get("/admin/outreach/resume/..%2Fx").status_code, 404)

    def test_replied_rows_link_to_the_resume_tab(self):
        self.sync({"leads_csv": LEADS})
        self.login()
        page = self.client.get("/admin/outreach").get_data(as_text=True)
        self.assertIn("/admin/outreach/resume?company=Acme+AI", page)
        self.assertNotIn("company=Beta+Labs", page)


if __name__ == "__main__":
    unittest.main()
