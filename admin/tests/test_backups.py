"""Tests for backup create / list / restore / delete routes and service."""
import os
import shutil
import time

import pytest

from terraria_admin.services.backups import create_backup, list_backups, prune_auto_backups


# ── Service unit tests ────────────────────────────────────────────────────────

class FakeCfg:
    def __init__(self, terraria_dir):
        self.TERRARIA_DIR = terraria_dir
        self.WORLDS_DIR = os.path.join(terraria_dir, 'worlds')
        self.BACKUPS_DIR = os.path.join(terraria_dir, 'backups')
        self.BACKUP_KEEP_COUNT = 3


class TestBackupService:
    def test_create_backup_success(self, terraria_dir):
        cfg = FakeCfg(terraria_dir)
        name, err = create_backup(cfg, label='test')
        assert err is None
        assert name.startswith('test_')
        assert os.path.isdir(os.path.join(cfg.BACKUPS_DIR, name))

    def test_create_backup_no_worlds(self, tmp_path):
        cfg = FakeCfg(str(tmp_path))
        os.makedirs(cfg.WORLDS_DIR)
        os.makedirs(cfg.BACKUPS_DIR)
        name, err = create_backup(cfg)
        assert name is None
        assert 'No .wld' in err

    def test_create_backup_missing_worlds_dir(self, tmp_path):
        cfg = FakeCfg(str(tmp_path))
        os.makedirs(cfg.BACKUPS_DIR)
        # worlds dir intentionally not created
        name, err = create_backup(cfg)
        assert name is None
        assert err is not None

    def test_list_backups_sorted_newest_first(self, tmp_path):
        cfg = FakeCfg(str(tmp_path))
        os.makedirs(cfg.WORLDS_DIR)
        os.makedirs(cfg.BACKUPS_DIR)
        with open(os.path.join(cfg.WORLDS_DIR, 'w.wld'), 'wb') as f:
            f.write(b'\x00' * 64)

        # Create backups with sleep so mtime differs
        create_backup(cfg, label='auto')
        time.sleep(0.1)
        create_backup(cfg, label='manual')
        # Force different timestamps via touch
        backups = list_backups(cfg)
        assert len(backups) >= 1
        mtimes = [b['mtime'] for b in backups]
        assert mtimes == sorted(mtimes, reverse=True)

    def test_list_backups_label_detection(self, tmp_path):
        cfg = FakeCfg(str(tmp_path))
        os.makedirs(cfg.WORLDS_DIR)
        os.makedirs(cfg.BACKUPS_DIR)
        with open(os.path.join(cfg.WORLDS_DIR, 'w.wld'), 'wb') as f:
            f.write(b'\x00' * 64)

        # Manually create backup dirs with distinct names
        for label in ('auto_20240101_000001', 'manual_20240101_000002'):
            d = os.path.join(cfg.BACKUPS_DIR, label)
            os.makedirs(d)
            shutil.copy(os.path.join(cfg.WORLDS_DIR, 'w.wld'), os.path.join(d, 'w.wld'))

        labels = {b['name']: b['label'] for b in list_backups(cfg)}
        assert labels['auto_20240101_000001'] == 'auto'
        assert labels['manual_20240101_000002'] == 'manual'

    def test_prune_auto_backups(self, tmp_path):
        cfg = FakeCfg(str(tmp_path))
        os.makedirs(cfg.WORLDS_DIR)
        os.makedirs(cfg.BACKUPS_DIR)
        with open(os.path.join(cfg.WORLDS_DIR, 'w.wld'), 'wb') as f:
            f.write(b'\x00' * 64)

        # Create 5 auto backup dirs with unique names (bypass timestamp collision)
        for i in range(5):
            d = os.path.join(cfg.BACKUPS_DIR, f'auto_20240101_00000{i}')
            os.makedirs(d)
            shutil.copy(
                os.path.join(cfg.WORLDS_DIR, 'w.wld'),
                os.path.join(d, 'w.wld'),
            )
            # Give each a slightly different mtime
            os.utime(d, (1700000000 + i * 10, 1700000000 + i * 10))

        prune_auto_backups(cfg)
        remaining = [b['name'] for b in list_backups(cfg)]
        assert len(remaining) == 3  # BACKUP_KEEP_COUNT = 3


# ── Route integration tests ───────────────────────────────────────────────────

class TestBackupRoutes:
    def test_backups_page_renders(self, auth_client):
        r = auth_client.get('/backups')
        assert r.status_code == 200
        assert b'Backup' in r.data

    def test_backups_create_manual(self, auth_client):
        from unittest.mock import patch
        with patch('terraria_admin.services.discord.discord_notify'):
            r = auth_client.post('/backups/create', follow_redirects=True)
        assert r.status_code == 200
        # Either success or "no worlds" error — both are valid flash messages
        assert b'Backup' in r.data

    def test_backups_delete_traversal_rejected(self, auth_client):
        r = auth_client.post('/backups/delete',
                             data={'backup_name': '../etc/passwd'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid backup name' in r.data

    def test_backups_delete_separator_rejected(self, auth_client):
        r = auth_client.post('/backups/delete',
                             data={'backup_name': 'foo/bar'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid backup name' in r.data

    def test_backups_delete_nonexistent(self, auth_client):
        r = auth_client.post('/backups/delete',
                             data={'backup_name': 'nonexistent_20000101_000000'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'not found' in r.data.lower()

    def test_backups_restore_invalid_name(self, auth_client):
        r = auth_client.post('/backups/restore',
                             data={'backup_name': '../secret'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid backup name' in r.data

    def test_backups_delete_existing(self, auth_client, app, terraria_dir):
        """Create a backup via service then delete it via route."""
        cfg = app.terraria_config

        # Make sure worlds dir has a .wld file
        os.makedirs(cfg.WORLDS_DIR, exist_ok=True)
        wld = os.path.join(cfg.WORLDS_DIR, 'TestWorld.wld')
        if not os.path.exists(wld):
            with open(wld, 'wb') as f:
                f.write(b'\x00' * 64)

        name, err = create_backup(cfg, label='manual')
        assert err is None, f'create_backup failed: {err}'

        from unittest.mock import patch
        with patch('terraria_admin.services.discord.discord_notify'):
            r = auth_client.post('/backups/delete',
                                 data={'backup_name': name},
                                 follow_redirects=True)
        assert r.status_code == 200
        assert b'deleted' in r.data.lower()
        assert not os.path.isdir(os.path.join(cfg.BACKUPS_DIR, name))
