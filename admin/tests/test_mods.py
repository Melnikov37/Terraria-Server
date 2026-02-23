"""Tests for mod management routes and services."""
import io
import json
import os
from unittest.mock import patch, MagicMock

import pytest

from terraria_admin.services.mods import (
    get_enabled_mods, save_enabled_mods, list_mods,
    record_mod_installed, get_mod_meta, download_mod_from_workshop,
)


# ── Service unit tests ────────────────────────────────────────────────────────

class FakeModsCfg:
    def __init__(self, tmp_dir):
        self.MODS_DIR = os.path.join(tmp_dir, 'Mods')
        self.TERRARIA_DIR = tmp_dir
        self.KNOWN_WORKSHOP_IDS = {'CalamityMod': '2824688072'}
        os.makedirs(self.MODS_DIR, exist_ok=True)


class TestModService:
    def test_get_enabled_mods_empty(self, tmp_path):
        cfg = FakeModsCfg(str(tmp_path))
        assert get_enabled_mods(cfg) == {}

    def test_save_and_load_enabled_mods_true_only(self, tmp_path):
        """save_enabled_mods persists only active mods (list format).
        Disabled mods (False) are NOT stored — loading returns them absent."""
        cfg = FakeModsCfg(str(tmp_path))
        save_enabled_mods({'CalamityMod': True, 'ThoriumMod': False}, cfg)
        loaded = get_enabled_mods(cfg)
        assert loaded.get('CalamityMod') is True
        # ThoriumMod=False is not persisted
        assert 'ThoriumMod' not in loaded

    def test_save_and_load_multiple_active_mods(self, tmp_path):
        cfg = FakeModsCfg(str(tmp_path))
        save_enabled_mods({'ModA': True, 'ModB': True, 'ModC': True}, cfg)
        loaded = get_enabled_mods(cfg)
        assert loaded.get('ModA') is True
        assert loaded.get('ModB') is True
        assert loaded.get('ModC') is True

    def test_list_mods_empty_dir(self, tmp_path):
        cfg = FakeModsCfg(str(tmp_path))
        assert list_mods(cfg) == []

    def test_list_mods_finds_tmod_files(self, tmp_path):
        cfg = FakeModsCfg(str(tmp_path))
        for name in ('ModA.tmod', 'ModB.tmod'):
            with open(os.path.join(cfg.MODS_DIR, name), 'wb') as f:
                f.write(b'\x00' * 64)
        mods = list_mods(cfg)
        names = [m['name'] for m in mods]
        assert 'ModA' in names
        assert 'ModB' in names

    def test_download_uses_tmodloader_app_id_first(self, tmp_path):
        """download_mod_from_workshop tries App ID 1281930 before 105600.
        Simulates the case where the mod is in the tModLoader Workshop (1281930)
        but NOT in the Terraria Workshop (105600) — e.g. Calamity Mod.
        """
        cfg = FakeModsCfg(str(tmp_path))
        cfg.TERRARIA_APP_ID = '105600'

        steamcmd_home = str(tmp_path / 'steamcmd_home')
        # Pre-create the workshop dir under 1281930 (tModLoader) with a fake .tmod
        workshop_dir = os.path.join(
            steamcmd_home, 'Steam', 'steamapps', 'workshop',
            'content', '1281930', '2824688072'
        )
        os.makedirs(workshop_dir, exist_ok=True)
        tmod_path = os.path.join(workshop_dir, 'CalamityMod.tmod')
        with open(tmod_path, 'wb') as f:
            f.write(b'\x00' * 64)

        calls = []

        def fake_steamcmd(steamcmd_bin, app_id, workshop_id, home):
            calls.append(app_id)
            # Simulate: 105600 returns no dir, 1281930 returns the pre-created dir
            if app_id == '1281930':
                return MagicMock(stdout='', stderr=''), workshop_dir
            return MagicMock(stdout='', stderr=''), None

        with patch('terraria_admin.services.mods._run_steamcmd_download', side_effect=fake_steamcmd), \
             patch('terraria_admin.services.mods.os.makedirs'):
            mod_name, err = download_mod_from_workshop('/fake/steamcmd.sh', '2824688072', cfg)

        assert err is None
        assert mod_name == 'CalamityMod'
        # Must try 1281930 first
        assert calls[0] == '1281930'

    def test_download_falls_back_to_terraria_app_id(self, tmp_path):
        """Falls back to TERRARIA_APP_ID (105600) when 1281930 has no match."""
        cfg = FakeModsCfg(str(tmp_path))
        cfg.TERRARIA_APP_ID = '105600'

        steamcmd_home = str(tmp_path / 'steamcmd_home2')
        workshop_dir = os.path.join(
            steamcmd_home, 'Steam', 'steamapps', 'workshop',
            'content', '105600', '99999'
        )
        os.makedirs(workshop_dir, exist_ok=True)
        with open(os.path.join(workshop_dir, 'OldMod.tmod'), 'wb') as f:
            f.write(b'\x00' * 64)

        def fake_steamcmd(steamcmd_bin, app_id, workshop_id, home):
            if app_id == '105600':
                return MagicMock(stdout='', stderr=''), workshop_dir
            return MagicMock(stdout='', stderr=''), None

        with patch('terraria_admin.services.mods._run_steamcmd_download', side_effect=fake_steamcmd), \
             patch('terraria_admin.services.mods.os.makedirs'):
            mod_name, err = download_mod_from_workshop('/fake/steamcmd.sh', '99999', cfg)

        assert err is None
        assert mod_name == 'OldMod'

    def test_download_returns_error_when_both_app_ids_fail(self, tmp_path):
        """Returns an error message when neither app ID yields a workshop dir."""
        cfg = FakeModsCfg(str(tmp_path))
        cfg.TERRARIA_APP_ID = '105600'

        def fake_steamcmd(steamcmd_bin, app_id, workshop_id, home):
            return MagicMock(stdout='No match', stderr=''), None

        with patch('terraria_admin.services.mods._run_steamcmd_download', side_effect=fake_steamcmd), \
             patch('terraria_admin.services.mods.os.makedirs'):
            mod_name, err = download_mod_from_workshop('/fake/steamcmd.sh', '0000000', cfg)

        assert mod_name is None
        assert 'download failed' in err.lower()

    def test_record_and_get_mod_meta(self, tmp_path):
        cfg = FakeModsCfg(str(tmp_path))
        dest = os.path.join(cfg.MODS_DIR, 'CalamityMod.tmod')
        with open(dest, 'wb') as f:
            f.write(b'\x00' * 64)
        record_mod_installed('CalamityMod', dest, cfg, workshop_id='2824688072')
        meta = get_mod_meta(cfg)
        assert 'CalamityMod' in meta
        assert meta['CalamityMod']['workshop_id'] == '2824688072'


# ── Route integration tests ───────────────────────────────────────────────────

class TestModRoutes:
    def test_mods_page_renders(self, auth_client):
        r = auth_client.get('/mods')
        assert r.status_code == 200
        assert b'Mod' in r.data

    def test_mods_public_no_auth_required(self, client):
        r = client.get('/mods/public')
        assert r.status_code == 200

    def test_mods_toggle_requires_mod_name(self, auth_client):
        r = auth_client.post('/mods/toggle', data={'mod_name': ''}, follow_redirects=True)
        assert r.status_code == 200
        assert b'required' in r.data.lower()

    def test_mods_toggle_enables_mod(self, auth_client, app):
        cfg = app.terraria_config
        os.makedirs(cfg.MODS_DIR, exist_ok=True)
        mod_path = os.path.join(cfg.MODS_DIR, 'ToggleMod.tmod')
        with open(mod_path, 'wb') as f:
            f.write(b'\x00' * 64)

        r = auth_client.post('/mods/toggle', data={'mod_name': 'ToggleMod'}, follow_redirects=True)
        assert r.status_code == 200

        enabled = get_enabled_mods(cfg)
        assert enabled.get('ToggleMod') is True
        os.remove(mod_path)

    def test_mods_upload_non_tmod_rejected(self, auth_client):
        data = {
            'mod_file': (io.BytesIO(b'fake exe'), 'malicious.exe'),
        }
        r = auth_client.post('/mods/upload',
                             data=data,
                             content_type='multipart/form-data',
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'Only .tmod' in r.data

    def test_mods_upload_valid_tmod(self, auth_client, app):
        cfg = app.terraria_config
        os.makedirs(cfg.MODS_DIR, exist_ok=True)
        fake_tmod = b'\x00' * 512
        data = {
            'mod_file': (io.BytesIO(fake_tmod), 'UploadedMod.tmod'),
        }
        r = auth_client.post('/mods/upload',
                             data=data,
                             content_type='multipart/form-data',
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'uploaded' in r.data.lower()
        dest = os.path.join(cfg.MODS_DIR, 'UploadedMod.tmod')
        assert os.path.exists(dest)
        os.remove(dest)

    def test_mods_delete_traversal_rejected(self, auth_client, app):
        """Path traversal via mod_name is sanitised by secure_filename.
        The route ends up looking for MODS_DIR/passwd.tmod which doesn't exist."""
        r = auth_client.post('/mods/delete',
                             data={'mod_name': '../../../etc/passwd'},
                             follow_redirects=True)
        assert r.status_code == 200
        # Route should not succeed in deleting anything; it flashes "not found" or "invalid path"
        assert b'not found' in r.data.lower() or b'invalid' in r.data.lower()

    def test_mods_delete_nonexistent(self, auth_client):
        r = auth_client.post('/mods/delete',
                             data={'mod_name': 'NoSuchMod'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'not found' in r.data.lower()

    def test_mods_workshop_steamcmd_not_found(self, auth_client):
        """When steamcmd binary is absent, flash the install hint and redirect."""
        with patch('terraria_admin.blueprints.mods.shutil.which', return_value=None):
            r = auth_client.post('/mods/workshop',
                                 data={'workshop_id': '2824688072'},
                                 follow_redirects=True)
        assert r.status_code == 200
        assert b'steamcmd not found' in r.data.lower()
        assert b'install.sh' in r.data

    def test_mods_update_one_steamcmd_not_found(self, auth_client, app):
        """mods_update_one flashes steamcmd error when binary is absent."""
        cfg = app.terraria_config
        os.makedirs(cfg.MODS_DIR, exist_ok=True)
        # Create a tmod file and a meta entry so the route reaches the steamcmd check
        mod_path = os.path.join(cfg.MODS_DIR, 'SomeMod.tmod')
        with open(mod_path, 'wb') as f:
            f.write(b'\x00' * 64)
        from terraria_admin.services.mods import record_mod_installed
        record_mod_installed('SomeMod', mod_path, cfg, workshop_id='2824688072')

        with patch('terraria_admin.blueprints.mods.shutil.which', return_value=None):
            r = auth_client.post('/mods/update',
                                 data={'mod_name': 'SomeMod'},
                                 follow_redirects=True)
        assert r.status_code == 200
        assert b'steamcmd not found' in r.data.lower()
        os.remove(mod_path)

    def test_mods_update_all_steamcmd_not_found(self, auth_client):
        """mods_update_all flashes steamcmd error when binary is absent."""
        with patch('terraria_admin.blueprints.mods.shutil.which', return_value=None):
            r = auth_client.post('/mods/update_all', follow_redirects=True)
        assert r.status_code == 200
        assert b'steamcmd not found' in r.data.lower()

    def test_mods_workshop_non_numeric_id_rejected(self, auth_client):
        r = auth_client.post('/mods/workshop',
                             data={'workshop_id': 'abc123!'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid Workshop ID' in r.data

    def test_mods_search_renders(self, auth_client):
        r = auth_client.get('/mods/search')
        assert r.status_code == 200

    def test_mods_delete_existing(self, auth_client, app):
        cfg = app.terraria_config
        os.makedirs(cfg.MODS_DIR, exist_ok=True)
        mod_path = os.path.join(cfg.MODS_DIR, 'DeleteMe.tmod')
        with open(mod_path, 'wb') as f:
            f.write(b'\x00' * 64)

        r = auth_client.post('/mods/delete',
                             data={'mod_name': 'DeleteMe'},
                             follow_redirects=True)
        assert r.status_code == 200
        assert b'deleted' in r.data.lower()
        assert not os.path.exists(mod_path)
