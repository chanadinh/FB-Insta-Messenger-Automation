import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from jinja2.exceptions import SecurityError, UndefinedError
from starlette.websockets import WebSocketDisconnect

import server
from fb_automation import auth
from fb_automation.engine import DEFAULT_CONFIG
from fb_automation.templates import render_message


class DashboardAccessTests(unittest.TestCase):
    def setUp(self):
        self.token = patch.object(auth, 'get_auth_token', return_value='review-test-token')
        self.token.start()
        self.addCleanup(self.token.stop)
        self.client = TestClient(server.app)
        self.addCleanup(self.client.close)

    def test_api_and_dashboard_require_authentication(self):
        self.assertEqual(self.client.get('/api/contacts').status_code, 401)
        self.assertEqual(self.client.put('/api/config', json={}).status_code, 401)
        self.assertEqual(self.client.get('/', follow_redirects=False).headers['location'], '/login')
        self.assertEqual(self.client.get('/login').status_code, 200)

    def test_login_uses_httponly_cookie_and_logout_revokes_it(self):
        self.assertEqual(self.client.post('/api/auth/login', json={'token': 'wrong'}).status_code, 401)
        response = self.client.post('/api/auth/login', json={'token': 'review-test-token'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('SameSite=strict', response.headers['set-cookie'])
        self.assertNotIn('review-test-token', response.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/contacts').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/contacts').status_code, 401)

    def test_bearer_authentication_and_origin_checks(self):
        headers = {'Authorization': 'Bearer review-test-token'}
        self.assertEqual(self.client.get('/api/contacts', headers=headers).status_code, 200)
        response = self.client.post('/api/start', headers={**headers, 'Origin': 'https://other.example'}, json={})
        self.assertEqual(response.status_code, 403)

    def test_websocket_requires_authentication_and_same_origin(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/ws'):
                self.fail('Unauthenticated WebSocket accepted')
        self.client.post('/api/auth/login', json={'token': 'review-test-token'})
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/ws', headers={'Origin': 'https://other.example'}):
                self.fail('Cross-origin WebSocket accepted')
        with self.client.websocket_connect('/ws', headers={'Origin': 'http://testserver'}) as ws:
            self.assertEqual(ws.receive_json()['type'], 'init')

    def test_config_updates_do_not_disclose_saved_api_key(self):
        config = {**DEFAULT_CONFIG, 'openai_api_key': 'sk-test-secret-value'}
        with patch.object(server.engine, 'load_config', return_value=dict(config)), \
             patch.object(server.engine, 'save_config'):
            response = self.client.put('/api/config', headers={'Authorization': 'Bearer review-test-token'}, json={})
        self.assertNotIn('sk-test-secret-value', response.text)

    def test_templates_preserve_contact_fields_but_block_python_globals(self):
        self.assertEqual(render_message('Hi {{first_name}}', {'first_name': 'Alex'}), 'Hi Alex')
        with self.assertRaises((SecurityError, UndefinedError)):
            render_message('{{ cycler.__init__.__globals__.os.name }}', {})
        with self.assertRaises((SecurityError, UndefinedError)):
            render_message('{{ first_name.__class__.__mro__ }}', {'first_name': 'Alex'})


class TokenStorageTests(unittest.TestCase):
    def test_sessions_expire_and_token_rotation_invalidates_them(self):
        with patch.object(auth, 'get_auth_token', return_value='first'), patch.object(auth.time, 'time', return_value=1000):
            cookie = auth.session_value()
            self.assertTrue(auth.authenticated({}, {auth.COOKIE_NAME: cookie}))
        with patch.object(auth, 'get_auth_token', return_value='first'), patch.object(auth.time, 'time', return_value=1000 + auth.SESSION_SECONDS + 1):
            self.assertFalse(auth.authenticated({}, {auth.COOKIE_NAME: cookie}))
        with patch.object(auth, 'get_auth_token', return_value='second'), patch.object(auth.time, 'time', return_value=1000):
            self.assertFalse(auth.authenticated({}, {auth.COOKIE_NAME: cookie}))

    def test_generated_token_is_persistent_and_private(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'APP_AUTH_TOKEN': ''}), \
             patch.object(auth, 'data_path', side_effect=lambda name: Path(tmp) / name):
            first = auth.get_auth_token()
            self.assertEqual(first, auth.get_auth_token())
            self.assertGreaterEqual(len(first), 32)
            self.assertEqual((Path(tmp) / '.dashboard_token').stat().st_mode & 0o777, 0o600)
