"""
Playwright E2E conftest.

Starts a live Flask server on a random port in a background thread,
then tears it down after the session.

Usage:
    pytest -m e2e --headed   # see the browser
    pytest -m e2e            # headless (CI default)
"""
import os
import shutil
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

ADMIN_TOKEN = 'e2e-secret-token'


def _make_mock_docker():
    container = MagicMock()
    container.status = 'running'
    container.logs.return_value = iter([b'[Server] E2E test line\n'])
    client = MagicMock()
    client.containers.get.return_value = container
    return client, container


@pytest.fixture(scope='session')
def live_app():
    """Session-scoped live Flask server for E2E tests."""
    terraria_dir = tempfile.mkdtemp(prefix='terraria_e2e_')
    for sub in ('worlds', 'backups', 'Mods'):
        os.makedirs(os.path.join(terraria_dir, sub))
    with open(os.path.join(terraria_dir, 'worlds', 'E2EWorld.wld'), 'wb') as f:
        f.write(b'\x00' * 128)

    os.environ['SECRET_KEY'] = 'e2e-key'
    os.environ['ADMIN_TOKEN'] = ADMIN_TOKEN
    os.environ['TERRARIA_DIR'] = terraria_dir
    os.environ['MODS_DIR'] = os.path.join(terraria_dir, 'Mods')
    os.environ['SERVER_CONTAINER'] = 'terraria-server'
    os.environ['SERVER_TYPE'] = 'tmodloader'
    os.environ['TESTING'] = '1'

    mock_client, _ = _make_mock_docker()

    with patch('docker.from_env', return_value=mock_client):
        from terraria_admin import create_app
        flask_app = create_app()

    flask_app.config['TESTING'] = True

    import socket
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()

    server_thread = threading.Thread(
        target=lambda: flask_app.run(host='127.0.0.1', port=port, use_reloader=False),
        daemon=True,
    )
    server_thread.start()
    time.sleep(0.5)  # give server time to start

    yield f'http://127.0.0.1:{port}', ADMIN_TOKEN

    shutil.rmtree(terraria_dir, ignore_errors=True)


@pytest.fixture(scope='session')
def base_url(live_app):
    url, _ = live_app
    return url


@pytest.fixture(scope='session')
def admin_token(live_app):
    _, token = live_app
    return token
