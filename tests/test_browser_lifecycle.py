import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fb_automation import browser, engine


class BrowserLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lock = asyncio.Lock()
        self.patchers = [patch.object(browser, '_browser_lock', self.lock),
                         patch.object(browser, '_active_context', None),
                         patch.object(browser, '_session_status_cache', {})]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_status_during_send_does_not_restart_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            (profile / 'session').touch()
            context = Mock(pages=[Mock()], close=AsyncMock())
            with patch.object(browser, 'get_profile_dir', return_value=profile), \
                 patch.object(browser, '_open_persistent_context', new=AsyncMock(return_value=context)) as open_browser, \
                 patch.object(browser, '_stop_playwright', new=AsyncMock()) as stop:
                live, _ = await browser.launch_browser(profile_name='Main')
                status = await browser.check_session_status('Main')
                self.assertTrue(status['busy'])
                self.assertTrue(engine.AutomationEngine().is_busy())
                open_browser.assert_awaited_once()
                stop.assert_not_awaited()
                await browser.close_browser(live)
                stop.assert_awaited_once()
                self.assertFalse(self.lock.locked())

    async def test_launch_failure_releases_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            (profile / 'session').touch()
            with patch.object(browser, 'get_profile_dir', return_value=profile), \
                 patch.object(browser, '_open_persistent_context', new=AsyncMock(side_effect=RuntimeError('launch failed'))), \
                 patch.object(browser, '_stop_playwright', new=AsyncMock()):
                with self.assertRaisesRegex(RuntimeError, 'launch failed'):
                    await browser.launch_browser(profile_name='Main')
        self.assertFalse(self.lock.locked())

    async def test_setup_cannot_replace_active_browser(self):
        await self.lock.acquire()
        with patch.object(browser, '_setup_login_locked', new=AsyncMock()) as setup:
            with self.assertRaisesRegex(RuntimeError, 'Browser is busy'):
                await browser.setup_login()
        setup.assert_not_awaited()
        self.lock.release()

    async def test_close_failure_still_cleans_up(self):
        context = Mock(close=AsyncMock(side_effect=RuntimeError('close failed')))
        await self.lock.acquire()
        with patch.object(browser, '_active_context', context), \
             patch.object(browser, '_stop_playwright', new=AsyncMock()) as stop:
            with self.assertRaisesRegex(RuntimeError, 'close failed'):
                await browser.close_browser(context)
        stop.assert_awaited_once()
        self.assertFalse(self.lock.locked())
