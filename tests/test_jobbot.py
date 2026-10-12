import unittest
from unittest.mock import patch

import requests

from app import create_app

JOB = {
    "id": "url:abc123",
    "company": "Acme",
    "title": "Software Engineer",
    "url": "https://job-boards.greenhouse.io/acme/jobs/1",
    "ats": "greenhouse",
    "status": "dry_run_ok",
    "attempts": 1,
    "first_seen": "2026-10-07T08:00:00+00:00",
    "last_attempt": "2026-10-07T09:00:00+00:00",
    "note": "reached Submit (not clicked)",
    "missing_required": [],
    "has_screenshot": True,
    "submission": None,
}
DETAIL = dict(JOB, fields=[
    {"label": "First Name", "kind": "text", "required": True, "answer": "Jeremy", "source": "preset", "ok": True, "error": ""},
    {"label": "Why Acme?", "kind": "textarea", "required": False, "answer": "Because <b>robots</b>", "source": "llm", "ok": True, "error": ""},
    {"label": "Resume", "kind": "file", "required": True, "answer": "/home/deploy/getmeajob/data/resume.pdf", "source": "resume", "ok": True, "error": ""},
], validation_errors=[], application_location="New York, NY", submit_log=[])


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b"", content_type="application/json"):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.reason = "error"

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class JobBotPageTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test", JOBBOT_API_URL="http://bot.test", JOBBOT_API_TOKEN="tok")
        self.client = self.app.test_client()
        self.calls = []
        self.responses = {}
        patcher = patch("app.blueprints.jobbot.requests.request", side_effect=self.fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_request(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append((method, url, json, headers))
        path = url.removeprefix("http://bot.test")
        response = self.responses.get((method, path))
        if isinstance(response, Exception):
            raise response
        return response or FakeResponse(404, {"error": "no such job"})

    def login(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["csrf_token"] = "csrf"

    def test_pages_need_the_admin_login(self):
        for path in ("/admin/jobs/", "/admin/jobs/url:abc123", "/admin/jobs/url:abc123/screenshot"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/admin/login", response.headers["Location"])
        self.assertEqual(self.calls, [])

    def test_list_groups_jobs_and_flags_codes(self):
        self.login()
        waiting = dict(JOB, id="j2", company="Beta", submission={"status": "needs_code", "prompt": "code?"})
        applied = dict(JOB, id="j3", company="Gamma", status="applied")
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": [JOB, waiting, applied], "last_pass": None})
        page = self.client.get("/admin/jobs/").get_data(as_text=True)
        self.assertIn("Acme", page)
        self.assertNotIn("Gamma", page)  # applied jobs are on their own tab
        self.assertIn("Beta is waiting for an emailed verification code", page)
        self.assertIn('/admin/jobs/url:abc123"', page)
        self.assertEqual(self.calls[0][3], {"Authorization": "Bearer tok"})
        page = self.client.get("/admin/jobs/?show=applied").get_data(as_text=True)
        self.assertIn("Gamma", page)
        self.assertNotIn(">Acme<", page)

    def test_closed_and_skipped_jobs_leave_needs_attention(self):
        self.login()
        failed = {"status": "failed", "problem": {"kind": "site"}}
        broken = dict(JOB, id="j1", company="Broken", submission=failed)
        closed = dict(JOB, id="j2", company="Shut", status="skipped", closed=True, submission=dict(failed, problem={"kind": "closed"}))
        older = dict(JOB, id="j3", company="Older", submission=dict(failed, problem={"kind": "closed"}))
        skipped = dict(JOB, id="j4", company="Skipped", status="skipped", submission=failed)
        jobs = [broken, closed, older, skipped]
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": jobs, "last_pass": None})
        page = self.client.get("/admin/jobs/?show=attention").get_data(as_text=True)
        self.assertIn("Broken", page)
        for name in ("Shut", "Older", "Skipped"):
            self.assertNotIn(name, page)
        page = self.client.get("/admin/jobs/?show=closed").get_data(as_text=True)
        self.assertIn("Shut", page)
        self.assertIn("Older", page)
        self.assertNotIn("Broken", page)
        self.assertNotIn("Skipped", page)
        self.assertIn("jobs__badge--closed", page)

    def test_blocked_jobs_are_listed_to_apply_yourself(self):
        self.login()
        blocked = dict(JOB, id="j1", company="Captcha", status="blocked", blocked=True)
        flagged = dict(JOB, id="j2", company="Spam", blocked=True,
                       submission={"status": "unconfirmed", "problem": {"kind": "blocked"}})
        failed = dict(JOB, id="j3", company="Fixable", status="failed")
        jobs = [blocked, flagged, failed]
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": jobs, "last_pass": None})
        page = self.client.get("/admin/jobs/?show=blocked").get_data(as_text=True)
        self.assertIn("Captcha", page)
        self.assertIn("Spam", page)
        self.assertIn("Apply yourself", page)
        self.assertNotIn("Fixable", page)
        page = self.client.get("/admin/jobs/?show=attention").get_data(as_text=True)
        self.assertIn("Fixable", page)  # a failed dry run needs a look
        self.assertNotIn("Captcha", page)
        self.assertNotIn("Spam", page)

    def test_bot_down_shows_a_message(self):
        self.login()
        self.responses[("GET", "/api/jobs?limit=500")] = requests.ConnectionError("refused")
        response = self.client.get("/admin/jobs/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("not reachable", response.get_data(as_text=True))

    def test_detail_shows_answers_and_submit(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": DETAIL})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Submit application", page)
        self.assertIn("Because &lt;b&gt;robots&lt;/b&gt;", page)  # answers are escaped
        self.assertIn("resume.pdf", page)
        self.assertNotIn("/home/deploy", page)
        self.assertIn("/admin/jobs/url:abc123/screenshot", page)
        self.assertNotIn("Send code", page)

    def test_detail_lists_the_jobs_emails_linked_to_gmail(self):
        self.login()
        emails = [
            {"id": "e1", "direction": "received", "kind": "security_code", "subject": "Security code for Acme",
             "sender": "no-reply@greenhouse-mail.io", "recipient": "me@example.com", "at": "2026-10-07T09:05:00+00:00",
             "link": "https://mail.google.com/mail/u/me@gmail.com/#search/rfc822msgid%3Ax%40gh.io"},
            {"id": "e2", "direction": "sent", "kind": "code_needed", "subject": "[getmeajob] Code needed <now>",
             "sender": "me@gmail.com", "recipient": "alerts@example.com", "at": "2026-10-07T09:06:00+00:00", "link": ""},
        ]
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, emails=emails)})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Emails (2)", page)
        self.assertIn('href="https://mail.google.com/mail/u/me@gmail.com/#search/rfc822msgid%3Ax%40gh.io"', page)
        self.assertIn(">Security code for Acme<span class=\"sr\">", page)
        self.assertIn("[getmeajob] Code needed &lt;now&gt;", page)  # escaped, and no link without one
        self.assertIn("Sent by the bot", page)
        self.assertIn("no-reply@greenhouse-mail.io", page)
        self.assertIn("alerts@example.com", page)
        self.assertIn("Oct 07, 09:05 UTC", page)

    def test_company_email_kinds_have_labels(self):
        from app.blueprints.jobbot import jobbot_email_kind

        self.assertEqual(jobbot_email_kind("confirmation"), "Application received")
        self.assertEqual(jobbot_email_kind("rejection"), "Rejection")
        self.assertEqual(jobbot_email_kind("company"), "From the company")
        self.assertEqual(jobbot_email_kind("something_new"), "Something new")

    def test_detail_without_emails_says_so(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": DETAIL})  # an older bot
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Emails (0)", page)
        self.assertIn("No emails about this application yet", page)

    def test_detail_asks_for_a_code_and_offers_cancel(self):
        self.login()
        job = dict(DETAIL, submission={"status": "needs_code", "prompt": "Enter the 8-character code", "note": None,
                                       "updated_at": None, "has_screenshot": False})
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": job})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Enter the 8-character code", page)
        self.assertIn("Send code", page)
        self.assertIn("Cancel submission", page)
        self.assertNotIn("Submit application", page)
        self.assertIn('data-active="true"', page)

    def test_unconfirmed_submission_offers_a_forced_retry(self):
        self.login()
        job = dict(DETAIL, submission={"status": "unconfirmed", "prompt": None, "note": "clicked Submit but saw no confirmation",
                                       "updated_at": None, "has_screenshot": True})
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": job})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Retry submission anyway", page)
        self.assertIn('name="force" value="1"', page)
        self.assertIn("kind=submission", page)

    def test_submit_requires_csrf_and_calls_the_bot(self):
        self.login()
        self.responses[("POST", "/api/jobs/url%3Aabc123/submit")] = FakeResponse(202, {"submission": {"status": "queued"}})
        response = self.client.post("/admin/jobs/url:abc123/submit", data={})
        self.assertEqual(response.status_code, 302)
        self.assertEqual([c for c in self.calls if c[0] == "POST"], [])
        response = self.client.post("/admin/jobs/url:abc123/submit", data={"csrf_token": "csrf"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/jobs/url:abc123"))
        self.assertEqual(self.calls[-1][:3], ("POST", "http://bot.test/api/jobs/url%3Aabc123/submit", {"force": False}))

    def test_rerun_button_queues_a_rerun(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, status="failed")})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn('action="/admin/jobs/url:abc123/rerun"', page)
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, status="applied")})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertNotIn("/rerun", page)
        self.responses[("POST", "/api/jobs/url%3Aabc123/rerun")] = FakeResponse(202, {"edit": {"status": "queued"}})
        response = self.client.post("/admin/jobs/url:abc123/rerun", data={"csrf_token": "csrf"})
        self.assertTrue(response.headers["Location"].endswith("/admin/jobs/url:abc123#chat"))
        self.assertEqual(self.calls[-1][:3], ("POST", "http://bot.test/api/jobs/url%3Aabc123/rerun", {}))

    def test_code_and_errors_are_relayed(self):
        self.login()
        self.responses[("POST", "/api/jobs/url%3Aabc123/code")] = FakeResponse(409, {"error": "this job is not waiting for a code"})
        self.client.post("/admin/jobs/url:abc123/code", data={"csrf_token": "csrf", "code": "AB12CD34"})
        self.assertEqual(self.calls[-1][2], {"code": "AB12CD34"})
        with self.client.session_transaction() as session:
            self.assertIn(("error", "this job is not waiting for a code"), session["_flashes"])

    def test_screenshot_is_proxied(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123/screenshot?kind=review")] = FakeResponse(content=b"PNGDATA", content_type="image/png")
        response = self.client.get("/admin/jobs/url:abc123/screenshot")
        self.assertEqual((response.status_code, response.data, response.mimetype), (200, b"PNGDATA", "image/png"))
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_status_json_for_polling(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, submission={"status": "running"})})
        data = self.client.get("/admin/jobs/url:abc123/status.json").get_json()
        self.assertEqual(data["status"], "dry_run_ok")
        self.assertEqual(data["submission"], {"status": "running"})
        self.assertEqual(data["signature"], "dry_run_ok|running||")

    def test_chat_box_and_history(self):
        self.login()
        edits = [{"id": "e1", "message": "say I can start in June 2027", "status": "done",
                  "reply": "Updated your start date.", "created_at": "", "updated_at": "",
                  "changes": [{"label": "First Name", "education_index": None, "old": "Jeremy", "value": "Jay", "applied": True}]}]
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, edits=edits, editing=False)})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Ask for changes", page)
        self.assertIn('action="/admin/jobs/url:abc123/edit"', page)
        self.assertIn("say I can start in June 2027", page)
        self.assertIn("Updated your start date.", page)
        self.assertRegex(page, r"Jeremy\s*&rarr;\s*Jay")
        self.assertIn("jobs__row--edited", page)  # the changed answer is highlighted
        self.assertIn("Submit application", page)

    def test_chat_hides_buttons_while_editing(self):
        self.login()
        edits = [{"id": "e1", "message": "make it shorter", "status": "running", "reply": None, "changes": [],
                  "created_at": "", "updated_at": ""}]
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, edits=edits, editing=True)})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Working on it", page)
        self.assertIn("re-filling the form", page)
        self.assertNotIn("Submit application", page)
        self.assertNotIn('name="message"', page)
        self.assertIn('data-active="true"', page)

    def test_chat_message_is_sent_to_the_bot(self):
        self.login()
        self.responses[("POST", "/api/jobs/url%3Aabc123/edit")] = FakeResponse(202, {"edit": {"status": "queued"}})
        response = self.client.post("/admin/jobs/url:abc123/edit", data={"csrf_token": "csrf", "message": "pick Remote"})
        self.assertTrue(response.headers["Location"].endswith("/admin/jobs/url:abc123#chat"))
        self.assertEqual(self.calls[-1][:3], ("POST", "http://bot.test/api/jobs/url%3Aabc123/edit", {"message": "pick Remote"}))

    def test_unconfigured_bot(self):
        self.login()
        self.app.config["JOBBOT_API_TOKEN"] = None
        response = self.client.get("/admin/jobs/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
