import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fb_automation import engine


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_contacts_are_bounded_and_configured_delays_are_used(self):
        automation = engine.AutomationEngine()
        automation.load_config = lambda: {**engine.DEFAULT_CONFIG, 'max_concurrent_contacts': 2,
                                          'min_delay_seconds': 30, 'max_delay_seconds': 30}
        active = peak = processed = 0
        async def process(*_):
            nonlocal active, peak, processed
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1
            processed += 1
        automation._process_contact = process
        automation._wait_or_stop = AsyncMock(return_value=False)
        with patch.object(engine, 'get_active_profile', return_value='Main'), \
             patch.object(engine, 'launch_browser', new=AsyncMock(return_value=(Mock(), Mock()))), \
             patch.object(engine, 'close_browser', new=AsyncMock()):
            await automation._run_locked([{} for _ in range(100)])
        self.assertEqual(processed, 100)
        self.assertLessEqual(peak, 2)
        self.assertEqual(automation._wait_or_stop.await_count, 99)
        self.assertTrue(all(call.args == (30,) for call in automation._wait_or_stop.await_args_list))

    async def test_stop_interrupts_long_delay(self):
        automation = engine.AutomationEngine()
        task = asyncio.create_task(automation._wait_or_stop(3600))
        await asyncio.sleep(0)
        automation._stop_event.set()
        self.assertTrue(await asyncio.wait_for(task, timeout=1))

    async def test_stop_prevents_queued_contact_sends(self):
        automation = engine.AutomationEngine()
        automation.load_config = lambda: {**engine.DEFAULT_CONFIG, 'dry_run': True, 'max_concurrent_contacts': 1}
        calls = []
        async def process(*_):
            calls.append(True)
            automation._stop_event.set()
        automation._process_contact = process
        await automation._run_locked([{} for _ in range(10)])
        self.assertEqual(len(calls), 1)

    async def test_invalid_delay_range_is_not_saved(self):
        import server
        with patch.object(server.engine, 'load_config', return_value=dict(engine.DEFAULT_CONFIG)), \
             patch.object(server.engine, 'save_config') as save:
            result = await server.update_config(server.ConfigUpdate(min_delay_seconds=100, max_delay_seconds=1))
        self.assertFalse(result['ok'])
        save.assert_not_called()
