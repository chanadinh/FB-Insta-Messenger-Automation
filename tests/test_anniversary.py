import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import server


class AnniversarySendTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        for route in server.app.routes:
            if getattr(route, "path", "") == "/api/anniversary/send":
                app.router.routes.append(route)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.contacts = [
            {"first_name": "Other", "ig_url": ""},
            {"first_name": "Anni", "ig_url": "https://www.instagram.com/anni.test/"},
        ]
        contacts_patch = patch.object(server.engine, "load_contacts", return_value=self.contacts)
        contacts_patch.start()
        self.addCleanup(contacts_patch.stop)
        send_patch = patch.object(server.engine, "send_to_contact", new_callable=AsyncMock)
        self.send = send_patch.start()
        self.addCleanup(send_patch.stop)

    def test_send_uses_selected_contact_and_preserves_vietnamese(self):
        self.send.return_value = {"instagram": True}
        response = self.client.post("/api/anniversary/send", json={
            "contact_index": 1, "message": "  Thương em nhiều ❤️  ", "dry_run": False,
        })
        self.assertTrue(response.json()["ok"])
        self.send.assert_awaited_once_with(
            self.contacts[1], "Thương em nhiều ❤️", ["instagram"],
            profile_name=None, dry_run=False,
        )

    def test_missing_recipient_never_starts_a_send(self):
        for index in (0, 10):
            response = self.client.post("/api/anniversary/send", json={"contact_index": index, "message": "hello"})
            self.assertFalse(response.json()["ok"])
        self.send.assert_not_awaited()

    def test_failed_send_and_missing_login_are_reported(self):
        self.send.return_value = {"instagram": False}
        payload = {"contact_index": 1, "message": "hello", "dry_run": False}
        self.assertFalse(self.client.post("/api/anniversary/send", json=payload).json()["ok"])
        self.send.side_effect = RuntimeError("No browser profile. Use Setup Login first.")
        result = self.client.post("/api/anniversary/send", json=payload).json()
        self.assertFalse(result["ok"])
        self.assertIn("Setup Login", result["error"])


if __name__ == "__main__":
    unittest.main()
