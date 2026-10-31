import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fb_automation import scheduler
from fb_automation.logger import sent_message_matcher
from server import DashboardAuth


class DashboardAuthTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.get("/api/contacts")(lambda: [])

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

    def test_published_dashboard_without_a_password_stays_closed(self):
        app = FastAPI()
        app.get("/api/contacts")(lambda: [])
        app.add_middleware(DashboardAuth, required=True)
        self.assertEqual(TestClient(app).get("/api/contacts").status_code, 403)
        open_app = FastAPI()
        open_app.get("/api/contacts")(lambda: [])
        open_app.add_middleware(DashboardAuth)
        self.assertEqual(TestClient(open_app).get("/api/contacts").status_code, 200)  # local, nothing configured


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
