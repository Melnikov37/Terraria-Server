"""Tests for /players routes (list, kick, ban, ban by ID / unban)."""
from unittest.mock import patch

import pytest


class TestPlayersRoutes:
    def test_players_page_renders(self, auth_client):
        with patch('terraria_admin.blueprints.players.get_players') as m:
            m.return_value = [{'name': 'Alice'}, {'name': 'Bob'}]
            r = auth_client.get('/players')
        assert r.status_code == 200
        assert b'Players' in r.data

    def test_players_requires_auth(self, client):
        r = client.get('/players')
        assert r.status_code == 302

    def test_kick_player_sends_command(self, auth_client):
        # Patch screen_send where it is imported in the players blueprint
        with patch('terraria_admin.blueprints.players.screen_send', return_value=True) as mock_send:
            # Do NOT follow redirects — the redirect to /players would call get_players
            # which also calls screen_send('players', cfg) and pollutes mock counts
            r = auth_client.post('/players/kick', data={'player': 'Alice'})
        assert r.status_code == 302
        mock_send.assert_called_once()
        cmd_sent = mock_send.call_args[0][0]
        assert 'kick' in cmd_sent
        assert 'Alice' in cmd_sent

    def test_kick_player_empty_name_rejected(self, auth_client):
        with patch('terraria_admin.blueprints.players.screen_send', return_value=True) as mock_send:
            r = auth_client.post('/players/kick', data={'player': ''})
        assert r.status_code == 302
        # Empty name should NOT call screen_send
        mock_send.assert_not_called()

    def test_ban_player_sends_command(self, auth_client):
        with patch('terraria_admin.blueprints.players.screen_send', return_value=True) as mock_send, \
             patch('terraria_admin.services.discord.discord_notify'):
            r = auth_client.post('/players/ban', data={'player': 'Griefer'})
        assert r.status_code == 302
        mock_send.assert_called_once()
        cmd_sent = mock_send.call_args[0][0]
        assert 'ban' in cmd_sent
        assert 'Griefer' in cmd_sent

    def test_ban_empty_name_rejected(self, auth_client):
        with patch('terraria_admin.blueprints.players.screen_send', return_value=True) as mock_send:
            r = auth_client.post('/players/ban', data={'player': ''})
        assert r.status_code == 302
        mock_send.assert_not_called()

    def test_unban_tmodloader_shows_error(self, auth_client):
        """tModLoader doesn't support unban by ID — should flash an error."""
        r = auth_client.post('/players/unban', data={'id': '1'}, follow_redirects=True)
        assert r.status_code == 200
        # Should say unban is only for TShock
        assert b'TShock' in r.data or b'only available' in r.data.lower()
