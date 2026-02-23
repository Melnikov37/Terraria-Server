"""Tests for world management routes."""
import os
from unittest.mock import patch, MagicMock

import pytest


class TestWorldRoutes:
    def test_world_page_renders(self, auth_client):
        with patch('terraria_admin.blueprints.world.get_server_status') as ms, \
             patch('terraria_admin.services.world.list_worlds') as mw:
            ms.return_value = {'online': False}
            mw.return_value = []
            r = auth_client.get('/world')
        assert r.status_code == 200
        assert b'World' in r.data

    def test_world_requires_auth(self, client):
        r = client.get('/world')
        assert r.status_code == 302

    def test_broadcast_empty_message_rejected(self, auth_client):
        r = auth_client.post('/world/broadcast',
                             data={'message': ''},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'cannot be empty' in r.data.lower()

    def test_broadcast_sends_say_command(self, auth_client):
        # Patch where screen_send is imported in the world blueprint
        with patch('terraria_admin.blueprints.world.screen_send', return_value=True) as mock_send:
            r = auth_client.post('/world/broadcast',
                                 data={'message': 'Hello world!'},
                                 follow_redirects=False)
        assert r.status_code == 302
        mock_send.assert_called_once()
        cmd = mock_send.call_args[0][0]
        assert 'say' in cmd
        assert 'Hello world!' in cmd

    def test_run_command_empty_rejected(self, auth_client):
        r = auth_client.post('/world/command',
                             data={'command': ''},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'cannot be empty' in r.data.lower()

    def test_run_command_sends_to_server(self, auth_client):
        with patch('terraria_admin.blueprints.world.screen_send', return_value=True) as mock_send:
            r = auth_client.post('/world/command',
                                 data={'command': 'help'},
                                 follow_redirects=False)
        assert r.status_code == 302
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == 'help'

    def test_save_world_sends_save_command(self, auth_client):
        with patch('terraria_admin.blueprints.world.screen_send', return_value=True) as mock_send:
            r = auth_client.post('/world/save', follow_redirects=False)
        assert r.status_code == 302
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == 'save'

    def test_butcher_tmodloader_returns_error(self, auth_client):
        r = auth_client.post('/world/butcher', follow_redirects=True)
        assert r.status_code == 200
        assert b'only available for TShock' in r.data

    def test_world_switch_traversal_rejected(self, auth_client):
        r = auth_client.post('/world/switch',
                             data={'world_name': '../../../etc/shadow'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid world name' in r.data

    def test_world_switch_nonexistent_world(self, auth_client):
        r = auth_client.post('/world/switch',
                             data={'world_name': 'DoesNotExist'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'not found' in r.data.lower()

    def test_world_switch_existing_world(self, auth_client, app):
        cfg = app.terraria_config
        os.makedirs(cfg.WORLDS_DIR, exist_ok=True)
        world_path = os.path.join(cfg.WORLDS_DIR, 'SwitchTest.wld')
        with open(world_path, 'wb') as f:
            f.write(b'\x00' * 64)

        with patch('terraria_admin.blueprints.world.container_action'):
            r = auth_client.post('/world/switch',
                                 data={'world_name': 'SwitchTest'},
                                 follow_redirects=True)
        assert r.status_code == 200
        assert b'Switched' in r.data or b'Error' in r.data

        os.remove(world_path)

    def test_recreate_world_writes_evil_and_seed(self, auth_client, app):
        """recreate_world must write evil type and seed to serverconfig."""
        cfg = app.terraria_config
        os.makedirs(cfg.WORLDS_DIR, exist_ok=True)

        with patch('terraria_admin.blueprints.world.container_action'), \
             patch('terraria_admin.blueprints.world.time'):
            r = auth_client.post('/world/recreate',
                                 data={
                                     'worldname': 'TestWorld',
                                     'size': '2',
                                     'difficulty': '1',
                                     'evil': '2',
                                     'seed': 'not the bees',
                                 },
                                 follow_redirects=False)
        assert r.status_code == 302

        with open(cfg.CONFIG_FILE) as f:
            config = f.read()
        assert 'evil=2' in config
        assert 'seed=not the bees' in config

    def test_recreate_world_omits_seed_when_blank(self, auth_client, app):
        """When seed is blank, seed= line must NOT appear in serverconfig."""
        cfg = app.terraria_config
        os.makedirs(cfg.WORLDS_DIR, exist_ok=True)

        with patch('terraria_admin.blueprints.world.container_action'), \
             patch('terraria_admin.blueprints.world.time'):
            r = auth_client.post('/world/recreate',
                                 data={
                                     'worldname': 'TestWorld2',
                                     'size': '1',
                                     'difficulty': '0',
                                     'evil': '0',
                                     'seed': '',
                                 },
                                 follow_redirects=False)
        assert r.status_code == 302

        with open(cfg.CONFIG_FILE) as f:
            config = f.read()
        assert 'seed=' not in config

    def test_set_time_tmodloader_sends_cmd(self, auth_client):
        with patch('terraria_admin.blueprints.world.screen_send', return_value=True) as mock_send:
            r = auth_client.post('/world/time',
                                 data={'time': 'day'},
                                 follow_redirects=False)
        assert r.status_code == 302
        mock_send.assert_called_once()
        # 'day' maps to 'dawn' for tModLoader
        assert mock_send.call_args[0][0] == 'dawn'
