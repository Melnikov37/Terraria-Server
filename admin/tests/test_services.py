"""Unit tests for individual service functions."""
import os
import json
from unittest.mock import patch, MagicMock, call

import pytest


# ── screen.py ─────────────────────────────────────────────────────────────────

class TestScreenService:
    def _make_cfg(self, tmp_path):
        cfg = MagicMock()
        cfg.TERRARIA_DIR = str(tmp_path)
        cfg.SERVER_CONTAINER = 'terraria-server'
        return cfg

    def test_screen_send_no_fifo_returns_false(self, tmp_path):
        from terraria_admin.services.screen import screen_send
        cfg = self._make_cfg(tmp_path)
        # No FIFO exists → ENOENT → returns False
        result = screen_send('help', cfg)
        assert result is False

    def test_screen_send_with_fifo(self, tmp_path):
        from terraria_admin.services.screen import screen_send
        cfg = self._make_cfg(tmp_path)
        fifo = os.path.join(str(tmp_path), '.server-input')
        os.mkfifo(fifo)

        import threading
        received = []

        def reader():
            # Open in blocking mode on the READ side first,
            # so the writer can connect without ENXIO
            with open(fifo, 'r') as f:
                received.append(f.readline())

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        # Give the reader thread time to open the FIFO before we write
        import time
        time.sleep(0.05)

        result = screen_send('help', cfg)
        t.join(timeout=2)

        assert result is True
        assert 'help\n' in received

    def test_is_screen_running_container_running(self, tmp_path):
        from terraria_admin.services.screen import is_screen_running
        cfg = self._make_cfg(tmp_path)
        container = MagicMock()
        container.status = 'running'
        client = MagicMock()
        client.containers.get.return_value = container
        with patch('docker.from_env', return_value=client):
            result = is_screen_running(cfg)
        assert result is True
        client.close.assert_called_once()

    def test_is_screen_running_container_stopped(self, tmp_path):
        from terraria_admin.services.screen import is_screen_running
        cfg = self._make_cfg(tmp_path)
        container = MagicMock()
        container.status = 'exited'
        client = MagicMock()
        client.containers.get.return_value = container
        with patch('docker.from_env', return_value=client):
            result = is_screen_running(cfg)
        assert result is False

    def test_is_screen_running_docker_error(self, tmp_path):
        from terraria_admin.services.screen import is_screen_running
        cfg = self._make_cfg(tmp_path)
        with patch('docker.from_env', side_effect=Exception('No Docker')):
            result = is_screen_running(cfg)
        assert result is False


# ── server.py ─────────────────────────────────────────────────────────────────

class TestServerService:
    def _make_cfg(self, tmp_path):
        cfg = MagicMock()
        cfg.TERRARIA_DIR = str(tmp_path)
        cfg.SERVER_CONTAINER = 'terraria-server'
        cfg.SERVER_TYPE = 'tmodloader'
        cfg.REST_URL = 'http://127.0.0.1:7878'
        cfg.REST_TOKEN = ''
        cfg.MAX_PLAYERS = 8
        return cfg

    def test_container_action_stop(self, tmp_path):
        from terraria_admin.services.server import container_action
        cfg = self._make_cfg(tmp_path)
        container = MagicMock()
        client = MagicMock()
        client.containers.get.return_value = container
        with patch('docker.from_env', return_value=client):
            container_action('stop', cfg)
        container.stop.assert_called_once()
        client.close.assert_called_once()

    def test_container_action_start(self, tmp_path):
        from terraria_admin.services.server import container_action
        cfg = self._make_cfg(tmp_path)
        container = MagicMock()
        client = MagicMock()
        client.containers.get.return_value = container
        with patch('docker.from_env', return_value=client):
            container_action('start', cfg)
        container.start.assert_called_once()

    def test_container_action_restart(self, tmp_path):
        from terraria_admin.services.server import container_action
        cfg = self._make_cfg(tmp_path)
        container = MagicMock()
        client = MagicMock()
        client.containers.get.return_value = container
        with patch('docker.from_env', return_value=client):
            container_action('restart', cfg)
        container.restart.assert_called_once()

    def test_container_action_closes_client_on_exception(self, tmp_path):
        from terraria_admin.services.server import container_action
        cfg = self._make_cfg(tmp_path)
        client = MagicMock()
        client.containers.get.side_effect = Exception('not found')
        with patch('docker.from_env', return_value=client):
            with pytest.raises(Exception):
                container_action('stop', cfg)
        client.close.assert_called_once()


# ── discord.py ────────────────────────────────────────────────────────────────

class TestDiscordService:
    def test_discord_notify_no_webhook_does_nothing(self, tmp_path):
        from terraria_admin.services.discord import discord_notify
        cfg = MagicMock()
        cfg.DISCORD_CONFIG_FILE = str(tmp_path / '.discord.json')
        # Config file doesn't exist → no webhook → should not raise
        discord_notify('Test message', cfg)

    def test_discord_notify_sends_request(self, tmp_path):
        from terraria_admin.services.discord import discord_notify, save_discord_config
        cfg = MagicMock()
        cfg.DISCORD_CONFIG_FILE = str(tmp_path / '.discord.json')
        save_discord_config({'webhook_url': 'https://discord.com/api/webhooks/test'}, cfg)

        with patch('requests.post') as mock_post:
            discord_notify('Server started', cfg)
            import time; time.sleep(0.15)

        mock_post.assert_called_once()
        payload = mock_post.call_args[1]['json']
        assert 'embeds' in payload
        assert 'Server started' in payload['embeds'][0]['description']

    def test_discord_notify_event_disabled(self, tmp_path):
        from terraria_admin.services.discord import discord_notify, save_discord_config
        cfg = MagicMock()
        cfg.DISCORD_CONFIG_FILE = str(tmp_path / '.discord2.json')
        save_discord_config({
            'webhook_url': 'https://discord.com/api/webhooks/test',
            'notify_start': False,
        }, cfg)
        with patch('requests.post') as mock_post:
            discord_notify('Server started', cfg, event='start')
            import time; time.sleep(0.15)
        mock_post.assert_not_called()


# ── backups.py ────────────────────────────────────────────────────────────────

class TestBackupServiceEdgeCases:
    def test_list_backups_ignores_files_not_dirs(self, tmp_path):
        from terraria_admin.services.backups import list_backups
        cfg = MagicMock()
        cfg.BACKUPS_DIR = str(tmp_path / 'backups')
        os.makedirs(cfg.BACKUPS_DIR)
        with open(os.path.join(cfg.BACKUPS_DIR, 'stray.txt'), 'w') as f:
            f.write('junk')
        result = list_backups(cfg)
        assert result == []

    def test_list_backups_ignores_empty_dirs(self, tmp_path):
        from terraria_admin.services.backups import list_backups
        cfg = MagicMock()
        cfg.BACKUPS_DIR = str(tmp_path / 'backups2')
        os.makedirs(cfg.BACKUPS_DIR)
        empty_dir = os.path.join(cfg.BACKUPS_DIR, 'auto_20240101_000000')
        os.makedirs(empty_dir)
        result = list_backups(cfg)
        assert result == []
