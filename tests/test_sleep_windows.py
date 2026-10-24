import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from fb_automation import scheduler


class SleepWindowTests(unittest.IsolatedAsyncioTestCase):
    def test_daytime_window_wakes_same_day(self):
        job = dict(sleep_enabled=True, sleep_start_hour=9, sleep_end_hour=17)
        candidate = datetime(2026, 10, 24, 12, tzinfo=ZoneInfo('UTC'))
        self.assertEqual(scheduler.apply_sleep_window(job, candidate), candidate.replace(hour=17))

    def test_overnight_boundaries(self):
        job = dict(sleep_enabled=True, sleep_start_hour=22, sleep_end_hour=7)
        for hour, day, wake in [(21, 24, 21), (22, 25, 7), (2, 24, 7), (7, 24, 7)]:
            with self.subTest(hour=hour):
                candidate = datetime(2026, 10, 24, hour, tzinfo=ZoneInfo('UTC'))
                self.assertEqual(scheduler.apply_sleep_window(job, candidate), candidate.replace(day=day, hour=wake))

    async def test_overdue_job_defers_in_job_timezone(self):
        now = datetime(2026, 10, 25, 3, tzinfo=ZoneInfo('UTC'))  # 23:00 New York
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now.astimezone(tz) if tz else now.astimezone().replace(tzinfo=None)
        job = dict(id='job', enabled=True, timezone='America/New_York',
                   next_run='2026-10-24T20:00:00-04:00', sleep_enabled=True,
                   sleep_start_hour=22, sleep_end_hour=7)
        runner = scheduler.JobScheduler(Mock())
        runner.list_jobs = lambda: [job.copy()]
        runner._execute_job = AsyncMock()
        store = {'jobs': [job.copy()]}
        with patch.object(scheduler, 'datetime', Clock), \
             patch.object(scheduler, 'load_schedules', return_value=store), \
             patch.object(scheduler, 'save_schedules') as save:
            await runner._tick()
        runner._execute_job.assert_not_awaited()
        save.assert_called_once()
        self.assertEqual(store['jobs'][0]['next_run'], '2026-10-25T07:00:00-04:00')

    async def test_overdue_job_runs_when_awake(self):
        runner = scheduler.JobScheduler(Mock())
        job = dict(id='job', enabled=True, timezone='UTC', next_run='2000-01-01T00:00:00Z')
        runner.list_jobs = lambda: [job]
        runner._execute_job = AsyncMock()
        await runner._tick()
        runner._execute_job.assert_awaited_once_with(job)
