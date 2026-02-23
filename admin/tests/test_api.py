"""Tests for /api/* endpoints."""
import json
from unittest.mock import patch, MagicMock

import pytest


class TestApiStatus:
    def test_api_status_returns_json(self, auth_client):
        # Patch where it is used in the api blueprint
        with patch('terraria_admin.blueprints.api.get_server_status') as m:
            m.return_value = {'online': True, 'players': 2, 'max_players': 8, 'version': '1.4.4.9'}
            r = auth_client.get('/api/status')
        assert r.status_code == 200
        data = r.get_json()
        assert 'online' in data
        assert data['online'] is True

    def test_api_status_requires_auth(self, client):
        r = client.get('/api/status')
        assert r.status_code == 302


class TestApiPlayers:
    def test_api_players_returns_list(self, auth_client):
        with patch('terraria_admin.blueprints.api.get_players') as m:
            m.return_value = [{'name': 'Alice'}, {'name': 'Bob'}]
            r = auth_client.get('/api/players')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_api_players_empty_when_offline(self, auth_client):
        with patch('terraria_admin.blueprints.api.get_players') as m:
            m.return_value = []
            r = auth_client.get('/api/players')
        data = r.get_json()
        assert data == []


class TestApiVersion:
    def test_api_version_returns_json(self, auth_client):
        with patch('terraria_admin.blueprints.api.get_version_info') as m:
            m.return_value = {'terraria': '1.4.4.9', 'tmodloader': '2024.12'}
            r = auth_client.get('/api/version')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, dict)

    def test_api_version_requires_auth(self, client):
        r = client.get('/api/version')
        assert r.status_code == 302


class TestApiMods:
    def test_api_mods_returns_list(self, auth_client):
        with patch('terraria_admin.blueprints.api.list_mods') as m:
            m.return_value = [{'name': 'CalamityMod', 'enabled': True}]
            r = auth_client.get('/api/mods')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)

    def test_api_mods_requires_auth(self, client):
        r = client.get('/api/mods')
        assert r.status_code == 302


class TestApiLogs:
    def test_api_logs_returns_lines(self, auth_client, app):
        from terraria_admin.extensions import console_buffer, console_lock
        with console_lock:
            console_buffer.append('[Server] Hello from test')

        r = auth_client.get('/api/logs?lines=50')
        assert r.status_code == 200
        data = r.get_json()
        assert 'lines' in data
        assert isinstance(data['lines'], list)

    def test_api_logs_level_filter_error(self, auth_client, app):
        from terraria_admin.extensions import console_buffer, console_lock
        with console_lock:
            console_buffer.clear()
            console_buffer.append('[Server] ERROR something broke')
            console_buffer.append('[Server] normal line')

        r = auth_client.get('/api/logs?level=error&lines=100')
        assert r.status_code == 200
        data = r.get_json()
        # All returned lines should contain error keywords
        for line in data['lines']:
            assert any(kw in line.lower() for kw in ('error', 'exception', 'fail', 'fatal'))

    def test_api_logs_requires_auth(self, client):
        r = client.get('/api/logs')
        assert r.status_code == 302

    def test_api_logs_lines_capped_at_1000(self, auth_client):
        r = auth_client.get('/api/logs?lines=99999')
        assert r.status_code == 200
        data = r.get_json()
        # At most 1000 lines returned
        assert len(data.get('lines', [])) <= 1000


class TestApiMetrics:
    def test_api_metrics_returns_json(self, auth_client):
        r = auth_client.get('/api/metrics')
        assert r.status_code == 200
        data = r.get_json()
        # psutil may or may not be installed — both outcomes are valid
        assert isinstance(data, dict)
        assert 'error' in data or 'cpu_percent' in data


class TestLogsPage:
    def test_logs_page_renders(self, auth_client):
        r = auth_client.get('/logs')
        assert r.status_code == 200
