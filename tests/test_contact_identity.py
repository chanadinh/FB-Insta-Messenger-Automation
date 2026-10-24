import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fb_automation import engine, scheduler


class ContactIdentityTests(unittest.IsolatedAsyncioTestCase):
    def test_csv_migration_persists_ids_and_extra_columns(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(engine, 'CONTACTS_PATH', Path(tmp) / 'contacts.csv'):
            engine.CONTACTS_PATH.write_text('first_name,extra\nBob,keep me\n')
            first = engine.AutomationEngine.load_contacts()
            second = engine.AutomationEngine.load_contacts()
            self.assertTrue(first[0]['id'])
            self.assertEqual(first, second)
            self.assertEqual(second[0]['extra'], 'keep me')

    async def test_deleting_earlier_contact_does_not_redirect_reminder(self):
        rows = [dict(id=name, first_name=name) for name in ['Alice', 'Bob', 'Carol']]
        fake_engine = Mock()
        fake_engine.load_contacts.side_effect = lambda: rows[:]
        fake_engine.is_busy.return_value = False
        fake_engine.send_to_contact = AsyncMock(return_value={'instagram': True})
        runner = scheduler.JobScheduler(fake_engine)
        runner._resolve_message = lambda *_: 'For Bob'
        job = dict(id='job', name='Bob reminder', contact_index=1, platforms=['instagram'], timezone='UTC')
        store = {'jobs': [job]}
        with patch.object(scheduler, 'load_schedules', return_value=store), patch.object(scheduler, 'save_schedules'):
            migrated = runner.list_jobs()[0]
            self.assertEqual(migrated['contact_id'], 'Bob')
            rows.pop(0)
            current = runner.list_jobs()[0]
            self.assertEqual(current['contact_index'], 0)
            result = await runner._execute_job(current)
            self.assertTrue(result['ok'])
            self.assertEqual(fake_engine.send_to_contact.call_args.args[0]['id'], 'Bob')
            rows.pop(0)
            fake_engine.send_to_contact.reset_mock()
            result = await runner._execute_job(runner.list_jobs()[0])
            self.assertEqual(result['error'], 'invalid_contact')
            fake_engine.send_to_contact.assert_not_awaited()

    def test_out_of_range_contact_cannot_create_reminder(self):
        fake_engine = Mock()
        fake_engine.load_contacts.return_value = []
        runner = scheduler.JobScheduler(fake_engine)
        with self.assertRaisesRegex(ValueError, 'Contact not found'):
            runner.create_job({'contact_index': 0})
