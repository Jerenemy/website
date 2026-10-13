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
        self.assertIn("Beta is waiting for an emailed verification code", page)
        self.assertIn('/admin/jobs/url:abc123"', page)
        self.assertEqual(self.calls[0][3], {"Authorization": "Bearer tok"})
        tracker, queue = page.split('id="queue"')
        self.assertIn("Gamma", tracker)  # a sent application is in the tracker, not the bot's queue
        self.assertNotIn("Gamma", queue)
        self.assertIn("Waiting to hear back", tracker)  # an older bot sends no stage: applied means waiting
        self.assertNotIn(">Acme<", tracker)

    def stage(self, key, label, source="email", email=None, unsorted=0, since="2026-10-12T10:00:00+00:00"):
        return {"key": key, "label": label, "source": source, "since": since, "email": email, "unsorted": unsorted,
                "auto": key}

    def tracker_jobs(self):
        email = {"kind": "rejection", "subject": "Your application to Delta", "at": "2026-10-13T13:20:00+00:00",
                 "link": "https://mail.google.com/mail/u/me@gmail.com/#search/rfc822msgid%3Ar%40x"}
        return [
            dict(JOB, id="w1", company="Waits", status="applied", applied_at="2026-10-11T08:00:00+00:00",
                 stage=self.stage("waiting", "Waiting to hear back", source="applied")),
            dict(JOB, id="r1", company="Delta", status="applied",
                 stage=self.stage("rejected", "Rejected", email=email, since=email["at"])),
            dict(JOB, id="i1", company="Forward", status="applied",
                 stage=self.stage("interviewing", "Moving forward", source="you", unsorted=1)),
            dict(JOB, id="q1", company="Queued"),  # a dry run: the bot's queue, not the tracker
        ]

    def test_tracker_lists_sent_applications_by_stage(self):
        self.login()
        unsorted = [{"message_id": "<m@x>", "kind": "rejection", "subject": "Regarding your application",
                     "sender": "avav@myworkday.com", "at": "2026-10-13T13:20:00+00:00", "why": "you applied to 2 jobs",
                     "link": "", "candidates": [
                         {"id": "i1", "company": "Forward", "title": "Software Engineer", "applied_at": "2026-10-11T08:00:00+00:00"},
                         {"id": "w1", "company": "Forward", "title": "Associate Software Engineer", "applied_at": "2026-10-13T05:00:00+00:00"}]}]
        payload = {"jobs": self.tracker_jobs(), "unsorted": unsorted, "last_pass": None}
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload=payload)
        page = self.client.get("/admin/jobs/").get_data(as_text=True)
        tracker, queue = page.split('id="queue"')
        # the board's numbers, then the applications grouped in stage order: moving forward, waiting, rejected
        self.assertIn('<span class="jobs__tile-n">1</span>\n            <span class="jobs__tile-name">Moving forward', tracker)
        self.assertLess(tracker.index(">Forward<"), tracker.index(">Waits<"))
        self.assertLess(tracker.index(">Waits<"), tracker.index(">Delta<"))
        self.assertIn("set by you", tracker)
        self.assertIn("1 email to sort", tracker)
        self.assertIn('href="https://mail.google.com/mail/u/me@gmail.com/#search/rfc822msgid%3Ar%40x"', tracker)
        self.assertIn("Nothing yet", tracker)
        self.assertIn('<option value="rejected" selected>', tracker)
        self.assertNotIn("Queued", tracker)
        self.assertIn("Queued", queue)
        # the email to sort, with a button per application it may be about and one for neither
        self.assertIn("1 email could be about more than one application", tracker)
        self.assertIn("Associate Software Engineer", tracker)
        self.assertIn("None of these", tracker)
        self.assertEqual(tracker.count('name="message_id" value="&lt;m@x&gt;"'), 3)
        page = self.client.get("/admin/jobs/?stage=rejected").get_data(as_text=True)
        tracker = page.split('id="queue"')[0]
        self.assertIn(">Delta<", tracker)
        self.assertNotIn(">Waits<", tracker)
        self.assertIn("Showing rejected only", tracker)

    def test_sorting_an_email_and_setting_a_stage_call_the_bot(self):
        self.login()
        self.responses[("POST", "/api/emails/assign")] = FakeResponse(payload={"emails": []})
        response = self.client.post("/admin/jobs/emails/assign", data={
            "csrf_token": "csrf", "message_id": "<m@x>", "job_id": "i1", "next": "/admin/jobs/?stage=all#tracker"})
        self.assertEqual(response.headers["Location"], "/admin/jobs/?stage=all#tracker")
        self.assertEqual(self.calls[-1][:3], ("POST", "http://bot.test/api/emails/assign", {"message_id": "<m@x>", "job_id": "i1"}))
        self.client.post("/admin/jobs/emails/assign", data={"csrf_token": "csrf", "message_id": "<m@x>", "job_id": ""})
        self.assertEqual(self.calls[-1][2], {"message_id": "<m@x>", "job_id": None})  # about none of them
        # never sent off the site, and never without the CSRF token
        response = self.client.post("/admin/jobs/emails/assign", data={"csrf_token": "csrf", "message_id": "x",
                                                                       "next": "https://evil.example/admin/jobs/"})
        self.assertEqual(response.headers["Location"], "/admin/jobs/#tracker")
        calls = len(self.calls)
        self.client.post("/admin/jobs/emails/assign", data={"message_id": "<m@x>", "job_id": "i1"})
        self.assertEqual(len(self.calls), calls)

        self.responses[("POST", "/api/jobs/url%3Aabc123/stage")] = FakeResponse(payload={"job": DETAIL})
        response = self.client.post("/admin/jobs/url:abc123/stage", data={"csrf_token": "csrf", "stage": "interviewing"})
        self.assertEqual(response.headers["Location"], "/admin/jobs/url:abc123#job-status")
        self.assertEqual(self.calls[-1][2], {"stage": "interviewing"})
        with self.client.session_transaction() as session:
            self.assertIn(("success", "Marked Moving forward."), session["_flashes"])

    def test_detail_says_where_the_application_stands(self):
        self.login()
        email = {"kind": "interview", "subject": "Next steps with Acme", "at": "2026-10-13T10:00:00+00:00", "link": ""}
        emails = [{"id": "e1", "direction": "received", "kind": "interview", "subject": "Next steps with Acme",
                   "sender": "jobs@acme.com", "recipient": "me@example.com", "at": "2026-10-13T10:00:00+00:00",
                   "link": "", "message_id": "<i@acme>", "match": "sure", "why": "it quotes the requisition number R123"},
                  {"id": "e2", "direction": "received", "kind": "rejection", "subject": "Acme update",
                   "sender": "jobs@acme.com", "recipient": "me@example.com", "at": "2026-10-14T10:00:00+00:00",
                   "link": "", "message_id": "<r@acme>", "match": "guess", "why": "you applied to 2 jobs at Acme"}]
        job = dict(DETAIL, status="applied", emails=emails,
                   stage=self.stage("interviewing", "Moving forward", email=email, unsorted=1, since=email["at"]))
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": job})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Where it stands", page)
        self.assertIn('jobs__badge--stage-interviewing">Moving forward', page)
        self.assertIn('From "Next steps with Acme", Oct 13.', page)
        self.assertIn("1 email may be about this application", page)
        self.assertIn('<option value="interviewing" selected>', page)
        self.assertIn("Filed here because it quotes the requisition number R123", page)
        self.assertIn("Not about this application", page)
        self.assertIn("It's about this one", page)

    def test_a_job_you_applied_to_yourself_can_be_tracked(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, status="blocked", stage=None)})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Applied to this one yourself?", page)
        self.assertNotIn("Where it stands", page)

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
        from app.blueprints.jobbot import jobbot_email_kind, jobbot_subject

        self.assertEqual(jobbot_subject("[External] Thank you for applying"), "Thank you for applying")
        self.assertEqual(jobbot_subject("Re: [External] x"), "Re: [External] x")

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
