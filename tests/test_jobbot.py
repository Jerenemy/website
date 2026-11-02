import unittest
from unittest.mock import patch

import requests

from app import create_app

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

    def test_old_addresses_go_to_the_same_page_on_sisyphus(self):
        for path, target in (
            ("/admin/jobs/", "https://sisyphus.fail/jobs"),
            ("/admin/jobs/?view=sent", "https://sisyphus.fail/jobs?view=sent"),
            ("/admin/jobs/url:abc123", "https://sisyphus.fail/jobs/url%3Aabc123"),
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.headers["Location"], target)
        self.assertEqual(self.calls, [])

    def test_a_phone_shortcut_forwards_a_text_with_its_own_token(self):
        self.app.config["JOBBOT_TEXT_TOKEN"] = "sms-token"
        filed = [{"job_id": "j1", "company": "Humana", "title": "Software Engineer 2", "kind": "assessment", "match": "sure"}]
        self.responses[("POST", "/api/texts")] = FakeResponse(payload={"message_id": "<sms-1@getmeajob>", "filed": filed})
        text = {"from": "+15025550100", "body": "Humana: complete your assessment", "at": "2026-10-27T10:00:00Z"}
        for token in (None, "tok", "wrong"):  # no token, the bot's own token, a wrong one
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            self.assertEqual(self.client.post("/admin/jobs/texts", json=text, headers=headers).status_code, 401)
        self.assertEqual(self.calls, [])
        response = self.client.post("/admin/jobs/texts", json=text, headers={"Authorization": "Bearer sms-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["summary"], "Humana: Software Engineer 2 (assessment)")
        method, url, payload, headers = self.calls[0]
        self.assertEqual((method, url, payload), ("POST", "http://bot.test/api/texts", text))
        self.assertEqual(headers, {"Authorization": "Bearer tok"})  # the bot gets its own token, not the phone's

    def test_text_forwarding_is_off_without_its_token(self):
        response = self.client.post("/admin/jobs/texts", json={"body": "hi"}, headers={"Authorization": "Bearer "})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
