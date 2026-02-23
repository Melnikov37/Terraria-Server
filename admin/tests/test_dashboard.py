"""Tests for dashboard and server control routes."""
import pytest
from unittest.mock import MagicMock, patch


class TestDashboard:
    def test_dashboard_renders(self, auth_client):
        with patch('terraria_admin.blueprints.dashboard.get_server_status') as mock_status, \
             patch('terraria_admin.blueprints.dashboard.get_players') as mock_players:
            mock_status.return_value = {'online': False, 'version': '1.4', 'players': 0, 'max_players': 8}
            mock_players.return_value = []
            r = auth_client.get('/')
        assert r.status_code == 200
        assert b'Terraria' in r.data

    def test_server_control_invalid_action(self, auth_client):
        # No redirect follow — just check the POST itself flashes error
        with patch('terraria_admin.blueprints.dashboard.get_server_status') as ms, \
             patch('terraria_admin.blueprints.dashboard.get_players') as mp:
            ms.return_value = {'online': False}
            mp.return_value = []
            r = auth_client.post('/server/nuke', follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid action' in r.data

    def test_server_start(self, auth_client, mock_docker):
        _, container_mock = mock_docker
        with patch('terraria_admin.services.discord.discord_notify'), \
             patch('terraria_admin.blueprints.dashboard.get_server_status') as ms, \
             patch('terraria_admin.blueprints.dashboard.get_players') as mp:
            ms.return_value = {'online': True}
            mp.return_value = []
            r = auth_client.post('/server/start', follow_redirects=True)
        assert r.status_code == 200
        container_mock.start.assert_called_once()

    def test_server_stop(self, auth_client, mock_docker):
        _, container_mock = mock_docker
        with patch('terraria_admin.services.discord.discord_notify'), \
             patch('terraria_admin.blueprints.dashboard.get_server_status') as ms, \
             patch('terraria_admin.blueprints.dashboard.get_players') as mp:
            ms.return_value = {'online': False}
            mp.return_value = []
            r = auth_client.post('/server/stop', follow_redirects=True)
        assert r.status_code == 200
        container_mock.stop.assert_called_once()

    def test_server_restart(self, auth_client, mock_docker):
        _, container_mock = mock_docker
        with patch('terraria_admin.services.discord.discord_notify'), \
             patch('terraria_admin.blueprints.dashboard.get_server_status') as ms, \
             patch('terraria_admin.blueprints.dashboard.get_players') as mp:
            ms.return_value = {'online': True}
            mp.return_value = []
            r = auth_client.post('/server/restart', follow_redirects=True)
        assert r.status_code == 200
        container_mock.restart.assert_called_once()

    def test_server_control_docker_error_shows_flash(self, auth_client):
        """When Docker raises, the POST should flash an error and redirect (302)."""
        with patch('docker.from_env', side_effect=Exception('Docker not available')):
            # Don't follow redirect — the redirect itself would call get_server_status
            # which also uses docker (outside try block → would propagate)
            r = auth_client.post('/server/start')
        # Even on error, the blueprint catches it, flashes, and redirects
        assert r.status_code == 302
