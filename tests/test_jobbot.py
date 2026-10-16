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

    def view(self, page):
        """The list's open view: its rows, after the sidebar."""
        return page.split('id="view-name"', 1)[1]

    def test_list_opens_on_what_needs_you_and_flags_codes(self):
        self.login()
        waiting = dict(JOB, id="j2", company="Beta", submission={"status": "needs_code", "prompt": "code?"})
        applied = dict(JOB, id="j3", company="Gamma", status="applied")
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": [JOB, waiting, applied], "last_pass": None})
        page = self.client.get("/admin/jobs/").get_data(as_text=True)
        self.assertEqual(self.calls[0][3], {"Authorization": "Bearer tok"})
        rows = self.view(page)  # a code can't wait: the list opens on it, with the box to type it in
        self.assertIn("Codes to enter", rows.split("</h2>")[0])
        self.assertIn(">Beta<", rows)
        self.assertIn('action="/admin/jobs/j2/code"', rows)
        self.assertNotIn(">Acme<", rows)

        page = self.client.get("/admin/jobs/?view=review").get_data(as_text=True)
        self.assertIn("Beta is waiting for the code they emailed you", page)  # on every other view, above it
        rows = self.view(page)
        self.assertIn(">Acme<", rows)
        self.assertIn('/admin/jobs/url:abc123"', rows)
        self.assertNotIn(">Gamma<", rows)

        rows = self.view(self.client.get("/admin/jobs/?view=sent").get_data(as_text=True))
        self.assertIn(">Gamma<", rows)  # a sent application is in the tracker, not the bot's queue
        self.assertIn("Waiting to hear back", rows)  # an older bot sends no stage: applied means waiting
        self.assertNotIn(">Acme<", rows)

    def test_list_opens_on_the_tracker_when_nothing_needs_you(self):
        self.login()
        applied = dict(JOB, id="j3", company="Gamma", status="applied")
        retry = dict(JOB, id="j4", company="Later", status="retry", retry={"retries": 1, "max_retries": 3, "next_at": None},
                     problem={"title": "Gemini was rate-limited", "action": "", "detail": "", "kind": "transient"})
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": [applied, retry], "last_pass": None})
        rows = self.view(self.client.get("/admin/jobs/").get_data(as_text=True))
        self.assertIn("All sent", rows.split("</h2>")[0])
        self.assertIn(">Gamma<", rows)
        rows = self.view(self.client.get("/admin/jobs/?view=active").get_data(as_text=True))
        self.assertIn(">Later<", rows)  # a job the bot retries on its own is in progress, not needing you
        self.assertIn("Gemini was rate-limited", rows)

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
        self.assertIn("Ready to review", self.view(page).split("</h2>")[0])  # the dry run comes first
        self.assertIn("Emails to sort", page.split('id="view-name"')[0])  # the email is a view of its own
        page = self.client.get("/admin/jobs/?view=sort").get_data(as_text=True)
        tracker = self.view(self.client.get("/admin/jobs/?view=sent").get_data(as_text=True))
        # the applications grouped in stage order: moving forward, waiting, rejected
        self.assertLess(tracker.index(">Forward<"), tracker.index(">Waits<"))
        self.assertLess(tracker.index(">Waits<"), tracker.index(">Delta<"))
        self.assertIn("set by you", tracker)
        self.assertIn("1 email to sort", tracker)
        self.assertIn('href="https://mail.google.com/mail/u/me@gmail.com/#search/rfc822msgid%3Ar%40x"', tracker)
        self.assertIn("Nothing from them yet", tracker)
        self.assertIn('<option value="rejected" selected>', tracker)
        self.assertNotIn(">Queued<", tracker)
        self.assertIn(">Queued<", self.view(self.client.get("/admin/jobs/?view=all").get_data(as_text=True)))
        # the email to sort, with a button per application it may be about and one for neither
        sort = self.view(page)
        self.assertIn("Until you pick, it doesn&#39;t change any stage", sort)
        self.assertIn("Associate Software Engineer", sort)
        self.assertIn("None of these", sort)
        self.assertEqual(sort.count('name="message_id" value="&lt;m@x&gt;"'), 3)
        for old in ("/admin/jobs/?stage=rejected", "/admin/jobs/?view=rejected"):  # the old address still works
            tracker = self.view(self.client.get(old).get_data(as_text=True))
            self.assertIn("Rejected", tracker.split("</h2>")[0])
            self.assertIn(">Delta<", tracker)
            self.assertNotIn(">Waits<", tracker)

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
        self.assertEqual(response.headers["Location"], "/admin/jobs/")
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
        self.assertIn("I applied: track it", page)
        self.assertIn('name="stage" value="waiting"', page)
        self.assertIn("Apply on their site", page)
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
        rows = self.view(self.client.get("/admin/jobs/?show=attention").get_data(as_text=True))
        self.assertIn(">Broken<", rows)
        for name in ("Shut", "Older", "Skipped"):
            self.assertNotIn(f">{name}<", rows)
        rows = self.view(self.client.get("/admin/jobs/?show=closed").get_data(as_text=True))
        self.assertIn(">Shut<", rows)
        self.assertIn(">Older<", rows)
        self.assertNotIn(">Broken<", rows)
        self.assertNotIn(">Skipped<", rows)
        self.assertIn("jobs__badge--closed", rows)
        rows = self.view(self.client.get("/admin/jobs/?view=skipped").get_data(as_text=True))
        self.assertIn(">Skipped<", rows)

    def test_a_clean_rerun_after_a_failed_submission_goes_back_to_review(self):
        self.login()
        failed = {"status": "failed", "updated_at": "2026-10-15T06:34:33+00:00", "problem": {"kind": "changed"}}
        rerun = dict(JOB, id="j1", company="Rerun", last_attempt="2026-10-15T14:05:35+00:00", submission=failed)
        stale = dict(JOB, id="j2", company="Stale", last_attempt="2026-10-15T06:27:11+00:00", submission=failed)
        unconfirmed = dict(JOB, id="j3", company="Unsure", last_attempt="2026-10-15T14:05:35+00:00",
                           submission=dict(failed, status="unconfirmed"))
        broken = dict(JOB, id="j4", company="Broken", status="failed", last_attempt="2026-10-15T14:05:35+00:00",
                      submission=failed)
        jobs = [rerun, stale, unconfirmed, broken]
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": jobs, "last_pass": None})
        rows = self.view(self.client.get("/admin/jobs/?show=review").get_data(as_text=True))
        self.assertIn(">Rerun<", rows)
        for name in ("Stale", "Unsure", "Broken"):
            self.assertNotIn(f">{name}<", rows)
        rows = self.view(self.client.get("/admin/jobs/?show=attention").get_data(as_text=True))
        for name in ("Stale", "Unsure", "Broken"):
            self.assertIn(f">{name}<", rows)
        self.assertNotIn(">Rerun<", rows)

    def test_skipped_jobs_have_a_view_of_their_own(self):
        self.login()
        skipped = dict(JOB, id="j1", company="Passed", status="skipped")
        shut = dict(JOB, id="j2", company="Shut", status="skipped", closed=True)
        jobs = [JOB, skipped, shut]
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": jobs, "last_pass": None})
        page = self.client.get("/admin/jobs/?view=skipped").get_data(as_text=True)
        self.assertIn('href="/admin/jobs/?view=skipped" aria-current="page"', page)
        rows = self.view(page)
        self.assertIn("Skipped", rows.split("</h2>")[0])
        self.assertIn(">Passed<", rows)
        self.assertNotIn(">Acme<", rows)
        self.assertNotIn(">Shut<", rows)  # a closed posting is closed, whoever skipped it
        rows = self.view(self.client.get("/admin/jobs/?view=review").get_data(as_text=True))
        self.assertNotIn(">Passed<", rows)

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

    def test_a_code_sent_from_the_list_comes_back_to_it(self):
        self.login()
        self.responses[("POST", "/api/jobs/url%3Aabc123/code")] = FakeResponse(payload={"submission": {"status": "running"}})
        response = self.client.post("/admin/jobs/url:abc123/code", data={
            "csrf_token": "csrf", "code": "AB12CD34", "next": "/admin/jobs/?view=review"})
        self.assertEqual(response.headers["Location"], "/admin/jobs/?view=review")
        response = self.client.post("/admin/jobs/url:abc123/code", data={
            "csrf_token": "csrf", "code": "AB12CD34", "next": "https://evil.example/admin/jobs/"})
        self.assertEqual(response.headers["Location"], "/admin/jobs/url:abc123")

    def test_times_read_as_how_long_ago(self):
        from datetime import datetime, timedelta, timezone

        from app.blueprints.jobbot import jobbot_ago, jobbot_source

        now = datetime.now(timezone.utc)
        self.assertEqual(jobbot_ago((now - timedelta(minutes=5, seconds=3)).isoformat()), "5m ago")
        self.assertEqual(jobbot_ago((now - timedelta(hours=3, minutes=1)).isoformat()), "3h ago")
        self.assertEqual(jobbot_ago((now + timedelta(minutes=30, seconds=5)).isoformat()), "in 30m")
        self.assertEqual(jobbot_ago((now - timedelta(days=20)).isoformat().replace("+00:00", "Z")),
                         (now - timedelta(days=20)).strftime("%b %d").replace(" 0", " "))  # over a week: the date
        self.assertEqual(jobbot_ago(None), "")
        self.assertEqual(jobbot_source("profile:links.linkedin"), "Profile")
        self.assertEqual(jobbot_source("llm"), "AI")

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

    def test_tailored_resume_is_proxied(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123/resume")] = FakeResponse(content=b"%PDF-1.4", content_type="application/pdf")
        response = self.client.get("/admin/jobs/url:abc123/resume.pdf")
        self.assertEqual((response.status_code, response.data, response.mimetype), (200, b"%PDF-1.4", "application/pdf"))
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.responses.clear()
        self.assertEqual(self.client.get("/admin/jobs/url:abc123/resume.pdf").status_code, 404)

    def test_detail_shows_the_tailored_resume(self):
        self.login()
        resume = {
            "keywords": ["RESTful APIs", "TypeScript", "Rust"],
            "coverage": {"before": ["TypeScript"], "after": ["TypeScript", "RESTful APIs"]},
            "bullets": [{"where": "Software Engineer Intern", "before": "Built REST APIs.", "after": "Built RESTful APIs.",
                         "added": ["RESTful APIs"], "unverified": ["web applications"]}],
            "projects": {"before": ["Zaychess"], "after": ["EAR"]},
            "skills": [{"label": "Languages", "before": ["Python"], "after": ["TypeScript", "Python", "version control"],
                        "unverified": ["version control"]}],
            "unsupported": ["Rust"],
            "refused": [{"where": "Zaychess", "text": "Built it in <Rust>.", "why": "names 'Rust', which resume.yaml does not"}],
            "created_at": "2026-10-14T09:00:00+00:00",
        }
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, resume=resume)})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Resume, tailored", page)
        self.assertIn("2 of 3 keywords on the page (was 1) · 1 you don't have", page)
        self.assertIn('class="jkey jkey--lacks"', page)
        self.assertIn("Check this is true: version control", page)
        self.assertIn('class="jkey jkey--added"', page)
        self.assertIn("<del class=\"jdiff__before\">Built REST APIs.</del>", page)
        self.assertIn("Check this is true: web applications", page)
        self.assertIn("EAR <span class=\"jresume__was\">instead of Zaychess</span>", page)
        self.assertIn("Built it in &lt;Rust&gt;.", page)
        self.assertIn('src="/admin/jobs/url:abc123/resume.pdf#navpanes=0&view=FitH"', page)

    def test_detail_lists_the_chats_resume_requests(self):
        self.login()
        resume = {"keywords": ["C++"], "coverage": {"before": [], "after": ["C++"]}, "created_at": "2026-10-15T09:00:00+00:00"}
        job = dict(DETAIL, resume=resume, resume_notes=["List C++ first on the Languages line.", "Show <EAR>."])
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": job})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Your requests", page)
        self.assertIn("<li>List C++ first on the Languages line.</li><li>Show &lt;EAR&gt;.</li>", page)
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, resume=resume)})
        self.assertNotIn("Your requests", self.client.get("/admin/jobs/url:abc123").get_data(as_text=True))

    def test_detail_without_a_tailored_resume_has_no_resume_panel(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, resume=None)})
        self.assertNotIn("Resume, tailored", self.client.get("/admin/jobs/url:abc123").get_data(as_text=True))

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
        self.assertRegex(page, r"Jeremy</span>\s*&rarr;\s*<span[^>]*>Jay")
        self.assertIn("jans--edited", page)  # the changed answer is highlighted
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

    def test_chat_messages_show_when_they_happened(self):
        self.login()
        edits = [
            {"id": "e1", "message": "make it shorter", "status": "done", "reply": "Shortened it.", "changes": [],
             "created_at": "2026-10-07T09:00:00+00:00", "updated_at": "2026-10-07T09:04:00+00:00"},
            {"id": "e2", "message": "/rerun triage", "by": "triage", "rerun": True, "status": "done", "reply": "Ran again.",
             "changes": [], "created_at": "2026-10-08T10:00:00+00:00", "updated_at": "2026-10-08T10:05:00+00:00"},
        ]
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, edits=edits)})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        chat = page.split('id="chat-name"')[1].split("</section>")[0]
        self.assertIn('datetime="2026-10-07T09:00:00+00:00"', chat)  # you asked
        self.assertIn("Oct 07, 09:04 UTC", chat)  # the bot answered
        self.assertIn(">Triage</span>", chat)  # a rerun triage queued says so
        self.assertIn("Reran the job to check a fix", chat)
        self.assertNotIn("/rerun triage", chat)

    def test_a_note_is_shown_and_saved(self):
        self.login()
        job = dict(DETAIL, your_note={"text": "referred by Sam", "updated_at": "2026-10-07T09:00:00+00:00"})
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": job})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn(">referred by Sam</textarea>", page)
        self.responses[("POST", "/api/jobs/url%3Aabc123/note")] = FakeResponse(payload={"job": job})
        response = self.client.post("/admin/jobs/url:abc123/note", data={"csrf_token": "csrf", "note": " call Friday "})
        self.assertTrue(response.headers["Location"].endswith("/admin/jobs/url:abc123#note"))
        self.assertEqual(self.calls[-1][:3], ("POST", "http://bot.test/api/jobs/url%3Aabc123/note", {"note": "call Friday"}))
        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": [dict(JOB, your_note=job["your_note"])]})
        self.assertIn("Note: referred by Sam", self.client.get("/admin/jobs/?view=review").get_data(as_text=True))

    def test_asking_triage_about_a_job_and_withdrawing(self):
        self.login()
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": DETAIL})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn('action="/admin/jobs/url:abc123/triage"', page)
        self.responses[("POST", "/api/jobs/url%3Aabc123/triage")] = FakeResponse(202, {"job": DETAIL})
        response = self.client.post("/admin/jobs/url:abc123/triage", data={"csrf_token": "csrf", "request": "salary is wrong"})
        self.assertTrue(response.headers["Location"].endswith("/admin/jobs/url:abc123#triage"))
        self.assertEqual(self.calls[-1][:3], ("POST", "http://bot.test/api/jobs/url%3Aabc123/triage", {"message": "salary is wrong"}))

        asked = {"id": "t1", "requested": True, "message": "salary is wrong", "status": "queued", "outcome": None,
                 "reply": None, "pr": None, "tries": 0, "created_at": "2026-10-07T09:00:00+00:00", "picked_at": None,
                 "resolved_at": None, "reran": False, "action": None}
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, triage=asked, triage_history=[asked])})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertIn("Waiting for the next run", page)
        self.assertIn("Waiting for triage", page)
        self.assertIn('data-watching="true"', page)  # the page checks back for triage's answer
        self.assertNotIn('action="/admin/jobs/url:abc123/triage"', page)  # one request at a time
        self.assertIn('action="/admin/jobs/url:abc123/triage-cancel"', page)
        self.responses[("POST", "/api/jobs/url%3Aabc123/triage/cancel")] = FakeResponse(payload={"job": DETAIL})
        self.client.post("/admin/jobs/url:abc123/triage-cancel", data={"csrf_token": "csrf"})
        self.assertEqual(self.calls[-1][:2], ("POST", "http://bot.test/api/jobs/url%3Aabc123/triage/cancel"))

    def test_what_triage_left_for_you_is_up_front(self):
        self.login()
        done = {"id": "t1", "requested": True, "message": "salary is wrong", "status": "done", "outcome": "fixed",
                "reply": "The salary rule read the range wrong.", "pr": "https://github.com/x/getmeajob/pull/9", "tries": 1,
                "created_at": "2026-10-07T09:00:00+00:00", "picked_at": "2026-10-07T09:10:00+00:00",
                "resolved_at": "2026-10-07T09:40:00+00:00", "reran": False, "action": "rerun"}
        failed_job = dict(JOB, id="j2", company="Beta", triage=dict(done, outcome="failed", action="failed"))
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, triage=done, triage_history=[done])})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        alert = page.split('id="triage-alert"')[1].split("</div>\n      </div>")[0]
        self.assertIn("Triage fixed it but didn&#39;t rerun it", alert)
        self.assertIn('action="/admin/jobs/url:abc123/rerun"', alert)
        self.assertIn("The job hasn't run since.", page)
        self.assertIn("Fixed, not rerun", page)

        self.responses[("GET", "/api/jobs?limit=500")] = FakeResponse(payload={"jobs": [dict(JOB, triage=done), failed_job]})
        rows = self.view(self.client.get("/admin/jobs/?view=triage").get_data(as_text=True))
        self.assertIn("Triage fixed it but didn&#39;t rerun it: rerun it", rows)
        self.assertIn("Triage couldn&#39;t fix it", rows)

        reran = dict(done, outcome="rerun", reran=True, action=None)
        self.responses[("GET", "/api/jobs/url%3Aabc123")] = FakeResponse(payload={"job": dict(DETAIL, triage=reran, triage_history=[reran])})
        page = self.client.get("/admin/jobs/url:abc123").get_data(as_text=True)
        self.assertNotIn('id="triage-alert"', page)
        self.assertIn("The job ran again", page)


if __name__ == "__main__":
    unittest.main()
