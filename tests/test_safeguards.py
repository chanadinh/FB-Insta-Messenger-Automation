import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fb_automation import access, scheduler
from fb_automation.logger import sent_message_matcher
from server import DashboardAuth


class DashboardAuthTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.get("/api/contacts")(lambda: [])
        app.get("/api/mailbox")(lambda: {"ok": True})

        @app.websocket("/ws")
        async def ws(socket: WebSocket):
            await socket.accept()
            await socket.send_json({"ok": True})

        app.add_middleware(DashboardAuth, username="admin", password="secret")
        self.client = TestClient(app)
        self.auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secret").decode()}

    def test_dashboard_routes_require_the_password(self):
        response = self.client.get("/api/contacts")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Basic", response.headers["www-authenticate"])
        self.assertEqual(self.client.get("/api/contacts", headers=self.auth).status_code, 200)
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws"):
                pass
        with self.client.websocket_connect("/ws", headers=self.auth) as socket:
            self.assertEqual(socket.receive_json(), {"ok": True})

    def test_mailbox_keeps_its_own_token_auth(self):
        self.assertEqual(self.client.get("/api/mailbox").status_code, 200)


class AccessLinkTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict("os.environ", {"APP_DATA_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def _client(self, **auth):
        app = FastAPI()
        app.get("/api/contacts")(lambda: [])
        app.include_router(access.router)

        @app.websocket("/ws")
        async def ws(socket: WebSocket):
            await socket.accept()
            await socket.send_json({"ok": True})

        app.add_middleware(DashboardAuth, **auth)
        return TestClient(app, base_url="https://testserver")

    def _key(self, link):
        return link.split("#key=", 1)[1]

    def test_link_lets_a_browser_in_without_signing_in(self):
        links = access.create_links("https://dash.example.com", ["Anh", "Em"])
        self.assertTrue(links["Em"].startswith("https://dash.example.com/access#key="))
        client = self._client()
        self.assertEqual(client.get("/api/contacts").status_code, 403)
        self.assertEqual(client.get("/access").status_code, 200)

        response = client.post("/api/access/claim", json={"key": self._key(links["Em"])})
        self.assertEqual(response.json(), {"ok": True, "name": "Em"})
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertEqual(client.get("/api/contacts").status_code, 200)
        # Browsers resend the cookie on the WebSocket handshake; the test client does not.
        cookie_header = {"Cookie": f"{access.COOKIE_NAME}={self._key(links['Em'])}"}
        with client.websocket_connect("/ws", headers=cookie_header) as socket:
            self.assertEqual(socket.receive_json(), {"ok": True})
        with self.assertRaises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"Cookie": f"{access.COOKIE_NAME}=guess"}):
                pass

    def test_bad_revoked_and_rotated_links_are_refused(self):
        links = access.create_links("https://dash.example.com", ["Anh", "Em"])
        client = self._client()
        self.assertEqual(client.post("/api/access/claim", json={"key": "guess"}).status_code, 403)
        client.post("/api/access/claim", json={"key": self._key(links["Em"])})
        self.assertTrue(access.revoke("Em"))
        self.assertEqual(client.get("/api/contacts").status_code, 403)

        with self.assertRaises(ValueError):
            access.create_links("https://dash.example.com", ["Anh"])
        new_links = access.create_links("https://dash.example.com", ["Anh"], rotate=True)
        self.assertEqual(client.post("/api/access/claim", json={"key": self._key(links["Anh"])}).status_code, 403)
        self.assertEqual(client.post("/api/access/claim", json={"key": self._key(new_links["Anh"])}).status_code, 200)

    def test_only_two_people_and_published_dashboards_fail_closed(self):
        with self.assertRaises(ValueError):
            access.create_links("https://dash.example.com", ["A", "B", "C"])
        self.assertEqual(self._client().get("/api/contacts").status_code, 200)  # local, nothing configured
        self.assertEqual(self._client(required=True).get("/api/contacts").status_code, 403)


class SchedulerSafeguardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.object(scheduler, "SCHEDULES_PATH", Path(self.tmp.name) / "schedules.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.engine = AsyncMock()
        self.engine.is_busy = lambda: False
        self.engine.load_config = lambda: {}
        self.engine.load_contacts = lambda: [{"first_name": "A", "ig_url": "https://www.instagram.com/a/"}]
        self.jobs = scheduler.JobScheduler(self.engine)

    def _job(self, index, **extra):
        return self.jobs.create_job({
            "name": f"job {index}", "contact_index": index, "idea": "hi",
            "platforms": ["instagram"], "use_ai": False, **extra,
        })

    def test_deleting_a_contact_keeps_jobs_on_the_same_people(self):
        before, target, after = self._job(0), self._job(1), self._job(2)
        self.jobs.contact_deleted(1)
        stored = {job["id"]: job for job in self.jobs.list_jobs()}
        self.assertEqual(stored[before["id"]]["contact_index"], 0)
        self.assertFalse(stored[target["id"]]["enabled"])
        self.assertEqual(stored[after["id"]]["contact_index"], 1)

    async def test_edits_made_during_a_send_survive_and_failures_back_off(self):
        job = self._job(0)

        async def send(*args, **kwargs):
            self.jobs.toggle_job(job["id"], False)
            return {"instagram": True}

        self.engine.send_to_contact = send
        await self.jobs._execute_job(job)
        stored = self.jobs.get_job(job["id"])
        self.assertFalse(stored["enabled"])
        self.assertIsNotNone(stored["last_run"])

        missing = self._job(5)
        await self.jobs._execute_job(missing)
        next_run = scheduler._parse_datetime(self.jobs.get_job(missing["id"])["next_run"])
        self.assertGreater(next_run, scheduler.datetime.now().astimezone() + scheduler.timedelta(minutes=10))


class SentMessageMatcherTests(unittest.TestCase):
    def test_truncated_and_tagged_previews_match_but_short_replies_do_not(self):
        long_message = "Anh nhớ em nhiều lắm, hôm nay đi làm về mệt nhưng nghĩ tới em là vui liền luôn đó nha"
        is_sent = sent_message_matcher([
            f"[IG] {long_message}"[:80],
            "[IG] [reply] Ok anh tới liền",
            "[FB] [follow-up 2] Em ăn cơm chưa?",
        ])
        self.assertTrue(is_sent(long_message))
        self.assertTrue(is_sent("ok anh tới liền"))
        self.assertTrue(is_sent("Em ăn cơm chưa?"))
        self.assertFalse(is_sent("ok"))
        self.assertFalse(is_sent("Em"))


if __name__ == "__main__":
    unittest.main()
