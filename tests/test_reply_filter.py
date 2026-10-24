import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fb_automation import engine, instagram, logger, messenger
from fb_automation.reply_filter import matches_sent_message


class ReplyFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_outgoing_text_is_not_an_instagram_reply(self):
        outgoing = 'This is an outgoing message longer than the historical CSV preview limit. ' * 3
        page = Mock(evaluate=AsyncMock(return_value=[outgoing, 'Thanks, got it']))
        for history in [[f'[IG] {outgoing}'], [f'[IG] {outgoing}'[:80]]]:
            with self.subTest(history=history):
                result = await instagram._collect_visible_thread_text(page, history)
                self.assertEqual(result, ['Thanks, got it'])

    async def test_long_outgoing_text_is_not_a_facebook_reply(self):
        outgoing = 'A sufficiently long outgoing message to exceed the CSV preview truncation. ' * 3
        page = Mock(goto=AsyncMock(), wait_for_timeout=AsyncMock(),
                    evaluate=AsyncMock(return_value=[outgoing, 'Got your message']))
        with patch.object(messenger, '_fb_needs_login', new=AsyncMock(return_value=False)):
            result = await messenger.collect_fb_replies(page, 'https://facebook.com/messages/t/123', [f'[FB] {outgoing}'])
        self.assertEqual(result, ['Got your message'])

    def test_short_incoming_text_is_not_removed_as_outgoing_substring(self):
        self.assertFalse(matches_sent_message('Thanks', ['[IG] Thanks for meeting me yesterday']))
        self.assertTrue(matches_sent_message('Hello there', ['[FB] [reply] Hello there']))

    def test_log_migration_preserves_history_and_full_new_messages(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(logger, 'LOG_PATH', Path(tmp) / 'log.csv'):
            logger.LOG_PATH.write_text('timestamp,first_name,last_name,profile_url,status,message_preview\n2026,Alex,,thread,sent,Old message\n')
            outgoing = 'A long message. ' * 20
            logger.log_message({'profile_url': 'thread'}, 'sent', '[IG] ' + outgoing)
            rows = logger.load_message_log()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['message_preview'], 'Old message')
            self.assertEqual(rows[1]['message_text'], '[IG] ' + outgoing)
            self.assertEqual(len(rows[1]['message_preview']), 80)

    def test_dry_runs_do_not_hide_incoming_replies(self):
        rows = [dict(status='dry_run', profile_url='thread', message_text='Not sent'),
                dict(status='sent', profile_url='thread', message_text='Actually sent')]
        with patch.object(engine, 'load_message_log', return_value=rows):
            self.assertEqual(engine.AutomationEngine._sent_messages_by_url(), {'thread': ['Actually sent']})
