import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fb_automation import access, letters


class LettersTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict("os.environ", {"APP_DATA_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        links = access.create_links("https://dash.example.com", ["Anh", "Em"])
        app = FastAPI()
        app.include_router(letters.router)
        self.anh = TestClient(app, cookies={access.COOKIE_NAME: links["Anh"].split("#key=", 1)[1]})
        self.em = TestClient(app, cookies={access.COOKIE_NAME: links["Em"].split("#key=", 1)[1]})
        self.stranger = TestClient(app)

    def test_each_person_only_sees_letters_from_the_other(self):
        self.assertEqual(self.anh.post("/api/letters", json={"body": "Anh nhớ em"}).json()["recipient"], "Em")
        self.em.post("/api/letters", json={"body": "Em thương anh"})

        anh = self.anh.get("/api/letters").json()
        em = self.em.get("/api/letters").json()
        self.assertEqual((anh["me"], anh["partner"]), ("Anh", "Em"))
        self.assertEqual([letter["body"] for letter in anh["inbox"]], ["Em thương anh"])
        self.assertEqual([letter["body"] for letter in anh["sent"]], ["Anh nhớ em"])
        self.assertEqual([letter["body"] for letter in em["inbox"]], ["Anh nhớ em"])
        self.assertEqual(em["unread"], 1)

    def test_scheduled_letters_stay_hidden_until_their_time(self):
        future = (letters.now() + timedelta(days=2)).isoformat()
        letter = self.anh.post("/api/letters", json={"body": "Chúc mừng kỷ niệm", "deliver_at": future}).json()
        self.assertEqual(self.em.get("/api/letters").json()["inbox"], [])
        self.assertEqual(len(self.anh.get("/api/letters").json()["sent"]), 1)
        self.assertEqual(self.em.post(f"/api/letters/{letter['id']}/read").status_code, 404)

        with patch.object(letters, "now", return_value=letters.now() + timedelta(days=3)):
            inbox = self.em.get("/api/letters").json()["inbox"]
        self.assertEqual([item["body"] for item in inbox], ["Chúc mừng kỷ niệm"])

    def test_read_receipts_and_cancelling_only_work_for_the_right_person(self):
        delivered = self.anh.post("/api/letters", json={"body": "Đọc nhé"}).json()
        self.assertEqual(self.anh.post(f"/api/letters/{delivered['id']}/read").status_code, 404)
        self.assertEqual(self.em.post(f"/api/letters/{delivered['id']}/read").status_code, 200)
        self.assertEqual(self.em.get("/api/letters").json()["unread"], 0)
        self.assertIsNotNone(self.anh.get("/api/letters").json()["sent"][0]["read_at"])

        future = (letters.now() + timedelta(hours=5)).isoformat()
        scheduled = self.anh.post("/api/letters", json={"body": "Bất ngờ", "deliver_at": future}).json()
        self.assertEqual(self.em.delete(f"/api/letters/{scheduled['id']}").status_code, 404)
        self.assertEqual(self.anh.delete(f"/api/letters/{delivered['id']}").status_code, 404)  # already delivered
        self.assertEqual(self.anh.delete(f"/api/letters/{scheduled['id']}").status_code, 200)
        self.assertEqual(len(self.anh.get("/api/letters").json()["sent"]), 1)

    def test_visitors_without_a_link_and_bad_letters_are_refused(self):
        self.assertEqual(self.stranger.get("/api/letters").status_code, 401)
        self.assertEqual(self.stranger.post("/api/letters", json={"body": "hi"}).status_code, 401)
        self.assertEqual(self.anh.post("/api/letters", json={"body": "   "}).status_code, 422)
        self.assertEqual(self.anh.post("/api/letters", json={"body": "x" * 2001}).status_code, 422)
        too_far = (letters.now() + timedelta(days=4000)).isoformat()
        self.assertEqual(self.anh.post("/api/letters", json={"body": "hi", "deliver_at": too_far}).status_code, 422)

    def test_a_single_person_has_nobody_to_write_to(self):
        access.revoke("Em")
        self.assertIsNone(self.anh.get("/api/letters").json()["partner"])
        self.assertEqual(self.anh.post("/api/letters", json={"body": "hi"}).status_code, 409)


if __name__ == "__main__":
    unittest.main()
