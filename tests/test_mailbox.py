import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fb_automation.mailbox import create_links, database, router


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"APP_DATA_DIR": self.directory.name})
        self.env.start()
        self.links = create_links("https://example.test", "Alex", "Sam")
        self.keys = {person: parse_qs(urlsplit(link).fragment)["key"][0] for person, link in self.links.items()}
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.directory.cleanup()

    def headers(self, person):
        return {"Authorization": f"Bearer {self.keys[person]}"}

    def test_identity_requires_private_key(self):
        for headers in ({}, {"Authorization": "Bearer girlfriend"}):
            self.assertEqual(self.client.get("/api/mailbox", headers=headers).status_code, 401)
            self.assertEqual(self.client.post("/api/mailbox/messages", headers=headers, json={"body": "hi"}).status_code, 401)
        result = self.client.get("/api/mailbox", headers=self.headers("girlfriend"))
        self.assertEqual(result.json()["person"], {"id": "girlfriend", "name": "Sam"})
        self.assertEqual(result.headers["cache-control"], "no-store")

    def test_delivery_read_receipts_and_persistence(self):
        result = self.client.post("/api/mailbox/messages", headers=self.headers("you"), json={"body": "  Love you 💌\nAlways  ", "sender": "girlfriend"})
        self.assertEqual(result.status_code, 201)
        note_id = result.json()["id"]
        note = self.client.get("/api/mailbox", headers=self.headers("girlfriend")).json()["messages"][0]
        self.assertEqual(note["sender"], "you")
        self.assertEqual(note["recipient"], "girlfriend")
        self.assertEqual(note["body"], "Love you 💌\nAlways")
        self.assertIsNone(note["read_at"])
        path = f"/api/mailbox/messages/{note_id}/read"
        self.assertEqual(self.client.post(path, headers=self.headers("you")).status_code, 404)
        self.assertEqual(self.client.post(path, headers=self.headers("girlfriend")).status_code, 200)
        with database() as db:
            first_read = db.execute("SELECT read_at FROM messages").fetchone()[0]
            self.assertIsNotNone(first_read)
        self.client.post(path, headers=self.headers("girlfriend"))
        note = self.client.get("/api/mailbox", headers=self.headers("you")).json()["messages"][0]
        self.assertEqual(note["read_at"], first_read)
        response = self.client.post("/api/mailbox/messages", headers=self.headers("girlfriend"), json={"body": "Love you too"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.client.get("/api/mailbox", headers=self.headers("you")).json()["messages"]), 2)

    def test_validation_and_unknown_message(self):
        for body in ("", "   ", "x" * 2001):
            self.assertEqual(self.client.post("/api/mailbox/messages", headers=self.headers("you"), json={"body": body}).status_code, 422)
        self.assertEqual(self.client.post("/api/mailbox/messages/999/read", headers=self.headers("you")).status_code, 404)

    def test_rotation_preserves_notes_and_revokes_old_links(self):
        self.client.post("/api/mailbox/messages", headers=self.headers("you"), json={"body": "Keep me"})
        with self.assertRaises(ValueError):
            create_links("https://example.test", "Alex", "Sam")
        links = create_links("https://example.test", "Alex", "Sam", rotate=True)
        self.assertEqual(self.client.get("/api/mailbox", headers=self.headers("you")).status_code, 401)
        token = parse_qs(urlsplit(links["you"]).fragment)["key"][0]
        result = self.client.get("/api/mailbox", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(result.json()["messages"][0]["body"], "Keep me")
        with database() as db:
            hashes = [row[0] for row in db.execute("SELECT token_hash FROM people")]
        self.assertNotIn(token, hashes)


if __name__ == "__main__":
    unittest.main()
