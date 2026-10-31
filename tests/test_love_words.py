import asyncio
import os
import tempfile
import unicodedata
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fb_automation.browser import CookieAuthError
from fb_automation.engine import AutomationEngine, Status
from fb_automation.love_words import LoveWordsError, LoveWordsService, detect_love, normalize_thread

THREAD = "https://www.instagram.com/direct/t/123456789/"


class DetectionTests(unittest.TestCase):
    def test_vietnamese_accents_and_texting_slang(self):
        for text in ("Anh yêu em ❤️", "Em thương anh nhiều", "anh yeu em", "Nhớ ck quá", "iu vk", "VK ơi", "ck", "iuuuu", "anh iu em", "thương u"):
            with self.subTest(text=text):
                self.assertEqual(detect_love(text), "vi")
        self.assertEqual(detect_love(unicodedata.normalize("NFD", "Anh yêu em")), "vi")

    def test_english_texting_and_mixed_languages(self):
        for text in ("I love you", "love u", "luv u", "miss u", "ILY", "ilysm", "loveu", "u mean the world to me", "u r my everything", "Can't wait to see u"):
            with self.subTest(text=text):
                self.assertEqual(detect_love(text), "en")
        self.assertEqual(detect_love("I love u, vk ơi ❤️"), "mixed")

    def test_normal_chat_and_negations_are_not_keepsakes(self):
        for text in ("u home?", "Are u free at 5?", "Do you stock milk?", "Message", "Send", "I don't love you", "I do not miss u", "Anh không yêu em", "khum iu vk", "ko thương ck", "chưa yêu em", "What time is dinner?"):
            with self.subTest(text=text):
                self.assertIsNone(detect_love(text))

    def test_only_instagram_direct_thread_urls_are_accepted(self):
        self.assertEqual(normalize_thread(THREAD + "?igsh=example"), THREAD)
        self.assertEqual(normalize_thread(THREAD.rstrip("/")), THREAD)
        for url in ("https://www.instagram.com/anni/", "https://instagram.com.evil.test/direct/t/123/", "https://user@instagram.com/direct/t/123/", "https://example.test/direct/t/123/", "file:///direct/t/123/"):
            with self.subTest(url=url), self.assertRaises(LoveWordsError):
                normalize_thread(url)


class LoveWordsAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, {"APP_DATA_DIR": self.directory.name})
        env.start()
        self.addCleanup(env.stop)
        profile = patch("fb_automation.browser.get_active_profile", return_value="Main")
        profile.start()
        self.addCleanup(profile.stop)
        self.engine = Mock()
        self.engine.is_busy.return_value = False
        self.engine.collect_love_words = AsyncMock(return_value=["Anh yêu em", "love u", "vk ơi", "u home?", "I don't love you"])
        self.service = LoveWordsService(self.engine)
        app = FastAPI()
        app.include_router(self.service.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def configure(self, thread=THREAD, automatic=False):
        return self.client.put("/api/love-words/settings", json={"thread_url": thread, "auto_sync": automatic})

    def test_disabled_until_configured_and_invalid_threads_do_not_scan(self):
        initial = self.client.get("/api/love-words")
        self.assertFalse(initial.json()["settings"]["auto_sync"])
        self.assertEqual(initial.json()["notes"], [])
        self.assertEqual(initial.headers["cache-control"], "no-store")
        self.assertEqual(self.client.post("/api/love-words/sync").status_code, 422)
        self.assertEqual(self.configure("https://www.instagram.com/anni/").status_code, 422)
        self.engine.collect_love_words.assert_not_awaited()

    def test_scan_saves_only_matching_words_and_deduplicates(self):
        self.assertEqual(self.configure().status_code, 200)
        first = self.client.post("/api/love-words/sync").json()
        self.assertEqual(first["added"], 3)
        self.assertEqual({note["body"] for note in first["notes"]}, {"Anh yêu em", "love u", "vk ơi"})
        self.assertEqual(self.client.post("/api/love-words/sync").json()["added"], 0)
        self.engine.collect_love_words.assert_awaited_with(THREAD, profile_name="Main")
        self.assertIsNotNone(first["settings"]["last_checked"])
        # Reading the archive never starts a browser collection.
        calls = self.engine.collect_love_words.await_count
        self.client.get("/api/love-words")
        self.assertEqual(self.engine.collect_love_words.await_count, calls)

    def test_removed_suggestions_stay_removed_on_future_scans(self):
        self.configure()
        notes = self.client.post("/api/love-words/sync").json()["notes"]
        note_id = notes[0]["id"]
        self.assertEqual(self.client.delete(f"/api/love-words/{note_id}").status_code, 200)
        again = self.client.post("/api/love-words/sync").json()
        self.assertEqual(again["added"], 0)
        self.assertEqual(len(again["notes"]), 2)
        self.assertNotIn(note_id, [note["id"] for note in again["notes"]])

    def test_conversations_are_kept_separate_and_persist(self):
        self.configure()
        self.client.post("/api/love-words/sync")
        self.configure("https://www.instagram.com/direct/t/999/")
        self.assertEqual(self.client.get("/api/love-words").json()["notes"], [])
        self.configure()
        self.assertEqual(len(self.client.get("/api/love-words").json()["notes"]), 3)
        self.assertFalse(self.client.get("/api/love-words").json()["settings"]["auto_sync"])

    def test_busy_and_login_errors_do_not_destroy_saved_words(self):
        self.configure()
        self.client.post("/api/love-words/sync")
        self.engine.is_busy.return_value = True
        self.assertEqual(self.client.post("/api/love-words/sync").status_code, 409)
        self.engine.is_busy.return_value = False
        self.engine.collect_love_words.side_effect = CookieAuthError("No browser profile")
        failure = self.client.post("/api/love-words/sync")
        self.assertEqual(failure.json()["detail"]["code"], "login_required")
        saved = self.client.get("/api/love-words").json()
        self.assertEqual(len(saved["notes"]), 3)
        self.assertEqual(saved["settings"]["last_error"], "login_required")


class CollectionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, {"APP_DATA_DIR": self.directory.name})
        env.start()
        self.addCleanup(env.stop)

    async def test_background_collection_requires_explicit_enablement(self):
        engine = Mock()
        engine.is_busy.return_value = False
        engine.collect_love_words = AsyncMock(return_value=["iu vk"])
        service = LoveWordsService(engine)
        task = asyncio.create_task(service.run())
        try:
            await asyncio.sleep(.05)
            engine.collect_love_words.assert_not_awaited()
            with patch("fb_automation.browser.get_active_profile", return_value="Main"):
                from fb_automation.love_words import LoveSettings
                await service.configure(LoveSettings(thread_url=THREAD, auto_sync=True))
            for _ in range(30):
                if engine.collect_love_words.await_count:
                    break
                await asyncio.sleep(.01)
            engine.collect_love_words.assert_awaited_once_with(THREAD, profile_name="Main")
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_reading_uses_shared_browser_lock_and_always_closes_browser(self):
        engine = AutomationEngine()
        context = Mock()
        context.new_page = AsyncMock(return_value=Mock())
        with patch("fb_automation.engine.launch_browser", AsyncMock(return_value=(context, Mock()))) as launch, patch("fb_automation.engine.close_browser", AsyncMock()) as close, patch("fb_automation.engine.collect_ig_love_words", AsyncMock(side_effect=LoveWordsError("chat_unavailable"))):
            with self.assertRaises(LoveWordsError):
                await engine.collect_love_words(THREAD, profile_name="Main")
            launch.assert_awaited_once_with(headless=True, need_fb=False, need_ig=True, profile_name="Main")
            close.assert_awaited_once_with(context)
        self.assertFalse(engine.is_busy())
        self.assertEqual(engine.state.status, Status.IDLE)


if __name__ == "__main__":
    unittest.main()
