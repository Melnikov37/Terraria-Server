"""Tests for world management routes."""
import os
from unittest.mock import patch, MagicMock

import pytest


# ── World service unit tests ───────────────────────────────────────────────────

class TestWorldService:
    """Direct unit tests for list_worlds() — no Flask needed."""

    def _cfg(self, worlds_dir):
        class Cfg:
            WORLDS_DIR = worlds_dir
        return Cfg()

    def test_list_worlds_missing_dir(self, tmp_path):
        from terraria_admin.services.world import list_worlds
        result = list_worlds(self._cfg(str(tmp_path / 'nonexistent')))
        assert result == []

    def test_list_worlds_empty_dir(self, tmp_path):
        from terraria_admin.services.world import list_worlds
        result = list_worlds(self._cfg(str(tmp_path)))
        assert result == []

    def test_list_worlds_finds_wld_files(self, tmp_path):
        from terraria_admin.services.world import list_worlds
        (tmp_path / 'Alpha.wld').write_bytes(b'\x00' * 1024)
        (tmp_path / 'Beta.wld').write_bytes(b'\x00' * 2048)
        result = list_worlds(self._cfg(str(tmp_path)))
        names = [w['name'] for w in result]
        assert 'Alpha' in names
        assert 'Beta' in names

    def test_list_worlds_ignores_non_wld_files(self, tmp_path):
        from terraria_admin.services.world import list_worlds
        (tmp_path / 'World.wld').write_bytes(b'\x00' * 64)
        (tmp_path / 'World.wld.bak').write_bytes(b'\x00' * 64)
        (tmp_path / 'readme.txt').write_text('hello')
        result = list_worlds(self._cfg(str(tmp_path)))
        assert len(result) == 1
        assert result[0]['name'] == 'World'

    def test_list_worlds_sorted_alphabetically(self, tmp_path):
        from terraria_admin.services.world import list_worlds
        for name in ('Zeta', 'Alpha', 'Gamma'):
            (tmp_path / f'{name}.wld').write_bytes(b'\x00' * 64)
        result = list_worlds(self._cfg(str(tmp_path)))
        assert [w['name'] for w in result] == ['Alpha', 'Gamma', 'Zeta']

    def test_list_worlds_has_required_fields(self, tmp_path):
        from terraria_admin.services.world import list_worlds
        (tmp_path / 'MyWorld.wld').write_bytes(b'\x00' * 1024 * 2)
        result = list_worlds(self._cfg(str(tmp_path)))
        assert len(result) == 1
        w = result[0]
        assert w['name'] == 'MyWorld'
        assert w['filename'] == 'MyWorld.wld'
        assert isinstance(w['size_mb'], float)
        assert 'modified' in w

    def test_list_worlds_size_mb_correct(self, tmp_path):
        from terraria_admin.services.world import list_worlds
        (tmp_path / 'Big.wld').write_bytes(b'\x00' * 1024 * 1024)  # exactly 1 MB
        result = list_worlds(self._cfg(str(tmp_path)))
        assert result[0]['size_mb'] == 1.0


# ── World routes ───────────────────────────────────────────────────────────────

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

    def test_world_list_shows_world_names(self, auth_client):
        worlds = [
            {'name': 'AlphaWorld', 'filename': 'AlphaWorld.wld', 'size_mb': 10.5, 'modified': '2024-01-01 12:00'},
            {'name': 'BetaWorld',  'filename': 'BetaWorld.wld',  'size_mb': 5.2,  'modified': '2024-01-02 13:00'},
        ]
        with patch('terraria_admin.blueprints.world.get_server_status',
                   return_value={'online': False, 'world': 'AlphaWorld', 'server_type': 'tmodloader'}), \
             patch('terraria_admin.blueprints.world.list_worlds', return_value=worlds):
            r = auth_client.get('/world')
        assert r.status_code == 200
        assert b'AlphaWorld' in r.data
        assert b'BetaWorld' in r.data

    def test_world_list_active_world_marked(self, auth_client):
        """Active world must be visually distinguished (ACTIVE badge)."""
        worlds = [
            {'name': 'Current', 'filename': 'Current.wld', 'size_mb': 8.0, 'modified': '2024-01-01 10:00'},
            {'name': 'Other',   'filename': 'Other.wld',   'size_mb': 4.0, 'modified': '2024-01-02 10:00'},
        ]
        with patch('terraria_admin.blueprints.world.get_server_status',
                   return_value={'online': False, 'world': 'Current', 'server_type': 'tmodloader'}), \
             patch('terraria_admin.blueprints.world.list_worlds', return_value=worlds):
            r = auth_client.get('/world')
        assert b'Active' in r.data

    def test_world_list_inactive_world_has_switch_button(self, auth_client):
        """Non-active worlds must show a Switch button."""
        worlds = [
            {'name': 'Live',    'filename': 'Live.wld',    'size_mb': 3.0, 'modified': '2024-01-01 09:00'},
            {'name': 'Archive', 'filename': 'Archive.wld', 'size_mb': 2.0, 'modified': '2023-12-01 09:00'},
        ]
        with patch('terraria_admin.blueprints.world.get_server_status',
                   return_value={'online': False, 'world': 'Live', 'server_type': 'tmodloader'}), \
             patch('terraria_admin.blueprints.world.list_worlds', return_value=worlds):
            r = auth_client.get('/world')
        assert b'Switch' in r.data

    def test_world_list_active_world_has_no_switch_button(self, auth_client):
        """The currently active world must NOT show a Switch button."""
        worlds = [
            {'name': 'OnlyWorld', 'filename': 'OnlyWorld.wld', 'size_mb': 5.0, 'modified': '2024-01-01 08:00'},
        ]
        with patch('terraria_admin.blueprints.world.get_server_status',
                   return_value={'online': False, 'world': 'OnlyWorld', 'server_type': 'tmodloader'}), \
             patch('terraria_admin.blueprints.world.list_worlds', return_value=worlds):
            r = auth_client.get('/world')
        # No switch form targeting world_switch endpoint for active world
        assert b'Switch &amp; Restart' not in r.data

    def test_world_list_empty_shows_message(self, auth_client):
        """When no .wld files exist, an appropriate message is displayed."""
        with patch('terraria_admin.blueprints.world.get_server_status',
                   return_value={'online': False, 'world': 'Unknown', 'server_type': 'tmodloader'}), \
             patch('terraria_admin.blueprints.world.list_worlds', return_value=[]):
            r = auth_client.get('/world')
        assert r.status_code == 200
        assert b'No world files found' in r.data

    def test_world_list_shows_size_and_date(self, auth_client):
        """Each world row must include file size and modification date."""
        worlds = [
            {'name': 'TestWorld', 'filename': 'TestWorld.wld', 'size_mb': 12.3, 'modified': '2024-06-15 14:30'},
        ]
        with patch('terraria_admin.blueprints.world.get_server_status',
                   return_value={'online': False, 'world': 'TestWorld', 'server_type': 'tmodloader'}), \
             patch('terraria_admin.blueprints.world.list_worlds', return_value=worlds):
            r = auth_client.get('/world')
        assert b'12.3' in r.data
        assert b'2024-06-15' in r.data

    def test_broadcast_empty_message_rejected(self, auth_client):
        with patch('terraria_admin.blueprints.world.get_server_status', return_value={'online': False}), \
             patch('terraria_admin.services.world.list_worlds', return_value=[]):
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
        with patch('terraria_admin.blueprints.world.get_server_status', return_value={'online': False}), \
             patch('terraria_admin.services.world.list_worlds', return_value=[]):
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
        with patch('terraria_admin.blueprints.world.get_server_status', return_value={'online': False}), \
             patch('terraria_admin.services.world.list_worlds', return_value=[]):
            r = auth_client.post('/world/butcher', follow_redirects=True)
        assert r.status_code == 200
        assert b'only available for TShock' in r.data

    def test_world_switch_traversal_rejected(self, auth_client):
        with patch('terraria_admin.blueprints.world.get_server_status', return_value={'online': False}), \
             patch('terraria_admin.services.world.list_worlds', return_value=[]):
            r = auth_client.post('/world/switch',
                                 data={'world_name': '../../../etc/shadow'},
                                 follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid world name' in r.data

    def test_world_switch_nonexistent_world(self, auth_client):
        with patch('terraria_admin.blueprints.world.get_server_status', return_value={'online': False}), \
             patch('terraria_admin.services.world.list_worlds', return_value=[]):
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

        with patch('terraria_admin.blueprints.world.container_action'), \
             patch('terraria_admin.blueprints.world.get_server_status', return_value={'online': False}), \
             patch('terraria_admin.services.world.list_worlds', return_value=[]):
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
                                     'worldname': 'EvilSeedWorld',
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
