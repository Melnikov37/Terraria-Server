"""Tests for mod management routes and services."""
import io
import json
import os
from unittest.mock import patch

import pytest

from terraria_admin.services.mods import (
    get_enabled_mods, save_enabled_mods, list_mods,
    record_mod_installed, get_mod_meta,
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
