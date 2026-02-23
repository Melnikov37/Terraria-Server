"""
Shared pytest fixtures for integration tests.

Key design decisions:
- TestConfig class with all paths pinned to a tmp dir (avoids class-level os.environ.get timing issues).
- TESTING env var prevents background schedulers from starting.
- Docker SDK is patched at the module level so no daemon is needed.
"""
import os
import json
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest


ADMIN_TOKEN = 'test-secret-token'


def _make_test_config_class(terraria_dir_path):
    """Return a Config-compatible class with all paths pinned to *terraria_dir_path*."""
    _mods_dir = os.path.join(terraria_dir_path, 'Mods')
    _token = ADMIN_TOKEN

    class TestConfig:
        SECRET_KEY = 'pytest-secret'
        SESSION_COOKIE_HTTPONLY = True
        PERMANENT_SESSION_LIFETIME = 3600
        MAX_CONTENT_LENGTH = 256 * 1024 * 1024

        TERRARIA_DIR = terraria_dir_path
        REST_URL = 'http://127.0.0.1:7878'
        REST_TOKEN = ''
        ADMIN_TOKEN = _token
        SERVER_TYPE = 'tmodloader'
        SCREEN_SESSION = 'terraria'
        SERVER_CONTAINER = 'terraria-server'
        LOG_FILE = None
        MODS_DIR = _mods_dir
        STEAMCMD_BIN = '/nonexistent/steamcmd.sh'
        TERRARIA_APP_ID = '105600'
        MOD_UPDATE_INTERVAL_HOURS = 0
        BACKUP_KEEP_COUNT = 24
        AUTO_BACKUP_INTERVAL_HOURS = 0
        SERVICE_NAME = 'terraria'
        ROLE_LEVELS = {'viewer': 0, 'admin': 1, 'superadmin': 2}
        MAX_CONSOLE_LINES = 500
        KNOWN_WORKSHOP_IDS = {'CalamityMod': '2824688072'}

        @property
        def CONFIG_FILE(self):
            return os.path.join(self.TERRARIA_DIR, 'serverconfig.txt')

        @property
        def TSHOCK_CONFIG(self):
            return os.path.join(self.TERRARIA_DIR, 'tshock', 'config.json')

        @property
        def WORLDS_DIR(self):
            return os.path.join(self.TERRARIA_DIR, 'worlds')

        @property
        def BACKUPS_DIR(self):
            return os.path.join(self.TERRARIA_DIR, 'backups')

        @property
        def ADMINS_FILE(self):
            return os.path.join(self.TERRARIA_DIR, '.admins.json')

        @property
        def DISCORD_CONFIG_FILE(self):
            return os.path.join(self.TERRARIA_DIR, '.discord.json')

    return TestConfig


def _make_mock_docker():
    """Return a pre-configured docker.from_env() mock."""
    container = MagicMock()
    container.status = 'running'
    container.logs.return_value = iter([b'[Server] Starting\n', b'Server started\n'])
    client = MagicMock()
    client.containers.get.return_value = container
    return client, container


@pytest.fixture(scope='session')
def terraria_dir():
    """Temporary /opt/terraria-like directory tree shared across all tests."""
    d = tempfile.mkdtemp(prefix='terraria_test_')
    for sub in ('worlds', 'backups', os.path.join('backups', 'placeholder'), 'Mods'):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    # Dummy world file so backup tests have something to copy
    with open(os.path.join(d, 'worlds', 'TestWorld.wld'), 'wb') as f:
        f.write(b'\x00' * 128)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope='session')
def app(terraria_dir):
    """
    Session-scoped Flask test application.

    Background schedulers are suppressed via TESTING env var.
    Docker is mocked so tests run without a Docker daemon.
    """
    os.environ['TESTING'] = '1'

    TestConfig = _make_test_config_class(terraria_dir)
    mock_client, _ = _make_mock_docker()

    with patch('docker.from_env', return_value=mock_client):
        from terraria_admin import create_app
        flask_app = create_app(config_class=TestConfig)

    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    return flask_app


@pytest.fixture()
def client(app):
    """Flask test client (unauthenticated)."""
    return app.test_client()


@pytest.fixture()
def auth_client(app):
    """Flask test client pre-authenticated as admin."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['logged_in'] = True
    return c


@pytest.fixture()
def mock_docker():
    """Patch docker.from_env for a single test, returns (client_mock, container_mock)."""
    client, container = _make_mock_docker()
    with patch('docker.from_env', return_value=client):
        yield client, container
