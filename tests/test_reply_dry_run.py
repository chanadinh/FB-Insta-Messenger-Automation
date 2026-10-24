import unittest
from unittest.mock import AsyncMock, patch

from fb_automation import engine


class ReplyDryRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_records_simulation_as_dry_run(self):
        import server
        row = {'platform': 'facebook', 'profile_url': 'thread'}
        with patch.object(server.engine, 'is_busy', return_value=False), \
             patch.object(server, 'load_replies', return_value=[row]), \
             patch.object(server.engine, 'send_reply_to_thread', new=AsyncMock(return_value={'ok': True, 'dry_run': True})), \
             patch.object(server, 'update_reply_status', return_value=row) as update:
            result = await server.send_reply(0, server.ReplySendRequest(message='Hello'))
        self.assertTrue(result['dry_run'])
        update.assert_called_once_with(0, 'Hello', 'dry_run')

    async def test_dry_run_never_opens_browser_or_sends(self):
        for platform in ('facebook', 'instagram'):
            with self.subTest(platform=platform):
                automation = engine.AutomationEngine()
                automation.load_config = lambda: {'dry_run': True}
                row = dict(platform=platform, profile_url='https://example.com/thread', first_name='Alex')
                with patch.object(engine, 'launch_browser', new=AsyncMock()) as launch, \
                     patch.object(engine, 'send_message', new=AsyncMock()) as fb, \
                     patch.object(engine, 'send_ig_message', new=AsyncMock()) as ig, \
                     patch.object(engine, 'log_message') as log:
                    result = await automation.send_reply_to_thread(row, 'Hello', profile_name='Main')
                self.assertEqual(result, {'ok': True, 'dry_run': True})
                launch.assert_not_awaited()
                fb.assert_not_awaited()
                ig.assert_not_awaited()
                self.assertEqual(log.call_args.args[1], 'dry_run')
                self.assertFalse(automation.is_busy())
                self.assertEqual(automation.state.status, engine.Status.IDLE)

    async def test_empty_message_rejected_before_browser_launch(self):
        automation = engine.AutomationEngine()
        with patch.object(engine, 'launch_browser', new=AsyncMock()) as launch:
            result = await automation.send_reply_to_thread({}, '  ')
        self.assertFalse(result['ok'])
        launch.assert_not_awaited()
