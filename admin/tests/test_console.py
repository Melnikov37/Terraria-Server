"""Tests for /console and /api/console/* routes."""
import json
from unittest.mock import patch, MagicMock

import pytest


class TestConsoleRoutes:
    def test_console_page_renders(self, auth_client):
        r = auth_client.get('/console')
        assert r.status_code == 200
        assert b'console' in r.data.lower()

    def test_console_page_requires_auth(self, client):
        r = client.get('/console')
        assert r.status_code == 302

    def test_api_console_lines_returns_json(self, auth_client, app):
        from terraria_admin.extensions import console_buffer, console_lock
        with console_lock:
            console_buffer.append('[Server] line1')
            console_buffer.append('[Server] line2')

        r = auth_client.get('/api/console/lines?since=0')
        assert r.status_code == 200
        data = r.get_json()
        assert 'lines' in data
        assert isinstance(data['lines'], list)

    def test_api_console_lines_since_filters(self, auth_client, app):
        from terraria_admin.extensions import console_buffer, console_lock
        with console_lock:
            existing = len(console_buffer)
            console_buffer.append('[Server] new-line-for-filter-test')

        r = auth_client.get(f'/api/console/lines?since={existing}')
        assert r.status_code == 200
        data = r.get_json()
        assert len(data['lines']) >= 1

    def test_api_console_send_success(self, auth_client):
        # Patch where screen_send is used in the console blueprint
        with patch('terraria_admin.blueprints.console.screen_send', return_value=True) as mock_send:
            r = auth_client.post(
                '/api/console/send',
                data=json.dumps({'cmd': 'help'}),
                content_type='application/json',
            )
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('ok') is True
        mock_send.assert_called_once()

    def test_api_console_send_empty_cmd_rejected(self, auth_client):
        r = auth_client.post(
            '/api/console/send',
            data=json.dumps({'cmd': ''}),
            content_type='application/json',
        )
        assert r.status_code == 200
        data = r.get_json()
        # Empty command returns ok=False with an error message
        assert data.get('ok') is False
        assert 'error' in data

    def test_api_console_send_requires_auth(self, client):
        r = client.post(
            '/api/console/send',
            data=json.dumps({'cmd': 'help'}),
            content_type='application/json',
        )
        assert r.status_code == 302

    def test_api_console_send_calls_screen_send(self, auth_client):
        """Verify the console send route calls screen_send with the given command."""
        with patch('terraria_admin.blueprints.console.screen_send', return_value=False) as mock_send:
            r = auth_client.post(
                '/api/console/send',
                data=json.dumps({'cmd': 'save'}),
                content_type='application/json',
            )
        # Blueprint always returns ok=True (fire-and-forget pattern)
        assert r.status_code == 200
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == 'save'
