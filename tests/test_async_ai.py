import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fb_automation import engine, scheduler


class AsyncAITests(unittest.IsolatedAsyncioTestCase):
    async def test_reminder_generation_keeps_event_loop_responsive(self):
        started, release = threading.Event(), threading.Event()
        fake_engine = Mock()
        fake_engine.is_busy.return_value = False
        fake_engine.load_contacts.return_value = [{'id': 'contact'}]
        fake_engine.send_to_contact = AsyncMock(return_value={'instagram': True})
        runner = scheduler.JobScheduler(fake_engine)
        def generate(*_):
            started.set()
            if not release.wait(2):
                raise TimeoutError('Event loop failed to release generator')
            return 'Reminder'
        runner._resolve_message = generate
        job = dict(id='job', name='Reminder', contact_index=0, contact_id='contact', platforms=['instagram'], timezone='UTC')
        with patch.object(scheduler, 'load_schedules', return_value={'jobs': [job]}), \
             patch.object(scheduler, 'save_schedules'):
            task = asyncio.create_task(runner._execute_job(job))
            try:
                await asyncio.wait_for(asyncio.to_thread(started.wait), 1)
                self.assertEqual(runner._running_job_id, 'job')
                self.assertEqual(await runner._execute_job(job, force=True), {'ok': False, 'error': 'busy'})
            finally:
                release.set()
                result = await task
        self.assertTrue(result['ok'])
        self.assertIsNone(runner._running_job_id)

    async def test_followup_generation_runs_outside_event_loop(self):
        main_thread = threading.get_ident()
        seen = []
        def generate(*args, **kwargs):
            seen.append(threading.get_ident())
            return []
        context = Mock()
        context.new_page = AsyncMock(return_value=Mock(close=AsyncMock()))
        automation = engine.AutomationEngine()
        with patch.object(engine, 'send_message', new=AsyncMock(return_value=True)), \
             patch.object(engine, 'log_message'), patch.object(engine, 'generate_follow_ups', side_effect=generate):
            await automation._send_on_platform(context, {}, 'Alex', 'thread', 'Hello', 'facebook', 'key', 'model', 1, 0, 0, 'casual')
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0], main_thread)
