"""Tests for /console routes, console poller service and check_player_event."""
import json
import time
import threading
from unittest.mock import patch, MagicMock, call

import pytest


# ── Route tests ───────────────────────────────────────────────────────────────

class TestConsoleRoutes:
    def test_console_page_renders(self, auth_client):
        r = auth_client.get('/console')
        assert r.status_code == 200
        assert b'console' in r.data.lower()

    def test_console_page_requires_auth(self, client):
        r = client.get('/console')
        assert r.status_code == 302

    def test_api_console_lines_returns_json(self, auth_client):
        from terraria_admin.extensions import console_buffer, console_lock
        with console_lock:
            console_buffer.append('[Server] route-test-line')

        r = auth_client.get('/api/console/lines?since=0')
        assert r.status_code == 200
        data = r.get_json()
        assert 'lines' in data
        assert 'total' in data
        assert isinstance(data['lines'], list)

    def test_api_console_lines_since_filters(self, auth_client):
        from terraria_admin import extensions
        from terraria_admin.extensions import console_buffer, console_lock
        with console_lock:
            before_seq = extensions.console_seq
            console_buffer.append('[Server] since-filter-test')
            extensions.console_seq += 1

        r = auth_client.get(f'/api/console/lines?since={before_seq}')
        data = r.get_json()
        assert any('since-filter-test' in l for l in data['lines'])

    def test_api_console_lines_since_at_total_returns_empty(self, auth_client):
        from terraria_admin.extensions import console_buffer, console_lock
        with console_lock:
            total = len(console_buffer)

        r = auth_client.get(f'/api/console/lines?since={total}')
        data = r.get_json()
        assert data['lines'] == []

    def test_api_console_lines_since_beyond_total_clamped(self, auth_client):
        """since > len(buf) must not raise — it is clamped to len(buf)."""
        r = auth_client.get('/api/console/lines?since=99999999')
        assert r.status_code == 200
        data = r.get_json()
        assert data['lines'] == []

    def test_api_console_lines_requires_auth(self, client):
        r = client.get('/api/console/lines?since=0')
        assert r.status_code == 302

    def test_api_console_send_success(self, auth_client):
        with patch('terraria_admin.blueprints.console.screen_send', return_value=True) as mock_send:
            r = auth_client.post(
                '/api/console/send',
                data=json.dumps({'cmd': 'help'}),
                content_type='application/json',
            )
        assert r.status_code == 200
        assert r.get_json().get('ok') is True
        mock_send.assert_called_once()

    def test_api_console_send_passes_command_to_screen_send(self, auth_client):
        with patch('terraria_admin.blueprints.console.screen_send', return_value=True) as mock_send:
            auth_client.post(
                '/api/console/send',
                data=json.dumps({'cmd': 'save'}),
                content_type='application/json',
            )
        assert mock_send.call_args[0][0] == 'save'

    def test_api_console_send_empty_cmd_rejected(self, auth_client):
        r = auth_client.post(
            '/api/console/send',
            data=json.dumps({'cmd': '   '}),
            content_type='application/json',
        )
        data = r.get_json()
        assert data.get('ok') is False
        assert 'error' in data

    def test_api_console_send_requires_auth(self, client):
        r = client.post(
            '/api/console/send',
            data=json.dumps({'cmd': 'help'}),
            content_type='application/json',
        )
        assert r.status_code == 302


# ── check_player_event unit tests ─────────────────────────────────────────────

class TestCheckPlayerEvent:
    def _run(self, line):
        from terraria_admin.services.console import check_player_event
        calls = []
        check_player_event(line, object(), lambda msg, cfg, **kw: calls.append((msg, kw)))
        return calls

    def test_join_event_detected(self):
        calls = self._run('Steve has joined')
        assert len(calls) == 1
        assert 'Steve' in calls[0][0]
        assert calls[0][1].get('event') == 'join'

    def test_leave_event_detected(self):
        calls = self._run('Alice has left')
        assert len(calls) == 1
        assert 'Alice' in calls[0][0]
        assert calls[0][1].get('event') == 'leave'

    def test_disconnect_event_detected(self):
        calls = self._run('Bob has disconnected')
        assert len(calls) == 1
        assert calls[0][1].get('event') == 'leave'

    def test_unrelated_line_fires_nothing(self):
        calls = self._run('[Server] World saved')
        assert calls == []

    def test_case_insensitive_join(self):
        calls = self._run('dave HAS JOINED')
        assert len(calls) == 1


# ── Console poller service tests ──────────────────────────────────────────────

@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestConsolePoller:
    """Tests for start_console_poller and its inner log-reading loop."""

    def _make_app(self, app):
        """Return a minimal app-like object with terraria_config."""
        return app

    def test_poller_requests_stdout_and_stderr(self, app):
        """Regression: container.logs() must be called with stdout=True, stderr=True.

        Before the fix, neither was specified (docker-py defaults both to False),
        so the Docker daemon returned no output and the buffer stayed empty.
        """
        from terraria_admin.extensions import console_buffer, console_lock

        mock_container = MagicMock()
        mock_container.logs.return_value = iter([])   # no lines — we only care about the call args
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        done = threading.Event()

        def fake_sleep(t):
            done.set()   # signal the test to stop waiting
            raise SystemExit  # break the infinite while-True loop

        with patch('docker.from_env', return_value=mock_client), \
             patch('terraria_admin.services.console.time.sleep', side_effect=fake_sleep):
            from terraria_admin.services.console import start_console_poller
            start_console_poller(app)
            done.wait(timeout=3)

        mock_container.logs.assert_called_once()
        call_kwargs = mock_container.logs.call_args[1]
        assert call_kwargs.get('stdout') is True,  'stdout=True must be passed'
        assert call_kwargs.get('stderr') is True,  'stderr=True must be passed'

    def test_poller_fills_buffer_from_docker_logs(self, app):
        """Lines from Docker container.logs() end up in console_buffer."""
        from terraria_admin.extensions import console_buffer, console_lock

        log_lines = [b'[Server] Hello world\n', b'[Server] Another line\n']

        mock_container = MagicMock()
        mock_container.logs.return_value = iter(log_lines)
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        done = threading.Event()

        def fake_sleep(t):
            done.set()
            raise SystemExit

        with console_lock:
            before = len(console_buffer)

        with patch('docker.from_env', return_value=mock_client), \
             patch('terraria_admin.services.console.time.sleep', side_effect=fake_sleep):
            from terraria_admin.services.console import start_console_poller
            start_console_poller(app)
            done.wait(timeout=3)

        with console_lock:
            new_lines = list(console_buffer)[before:]

        assert '[Server] Hello world' in new_lines
        assert '[Server] Another line' in new_lines

    def test_poller_splits_multiline_chunks(self, app):
        """Regression: a single Docker chunk with multiple \\n must become
        separate buffer entries, not one entry with embedded newlines.
        """
        from terraria_admin.extensions import console_buffer, console_lock

        # Docker may batch lines into one chunk
        chunk = b'[Server] line-A\n[Server] line-B\n[Server] line-C\n'

        mock_container = MagicMock()
        mock_container.logs.return_value = iter([chunk])
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        done = threading.Event()

        def fake_sleep(t):
            done.set()
            raise SystemExit

        with console_lock:
            before = len(console_buffer)

        with patch('docker.from_env', return_value=mock_client), \
             patch('terraria_admin.services.console.time.sleep', side_effect=fake_sleep):
            from terraria_admin.services.console import start_console_poller
            start_console_poller(app)
            done.wait(timeout=3)

        with console_lock:
            new_lines = list(console_buffer)[before:]

        assert '[Server] line-A' in new_lines, 'line-A must be a separate buffer entry'
        assert '[Server] line-B' in new_lines, 'line-B must be a separate buffer entry'
        assert '[Server] line-C' in new_lines, 'line-C must be a separate buffer entry'
        # No entry should contain an embedded newline
        assert all('\n' not in l for l in new_lines)

    def test_poller_strips_ansi_codes(self, app):
        """ANSI escape sequences must be removed from log lines."""
        from terraria_admin.extensions import console_buffer, console_lock

        ansi_line = b'\x1b[32m[Server] Green text\x1b[0m\n'

        mock_container = MagicMock()
        mock_container.logs.return_value = iter([ansi_line])
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        done = threading.Event()

        def fake_sleep(t):
            done.set()
            raise SystemExit

        with console_lock:
            before = len(console_buffer)

        with patch('docker.from_env', return_value=mock_client), \
             patch('terraria_admin.services.console.time.sleep', side_effect=fake_sleep):
            from terraria_admin.services.console import start_console_poller
            start_console_poller(app)
            done.wait(timeout=3)

        with console_lock:
            new_lines = list(console_buffer)[before:]

        assert any('[Server] Green text' in l for l in new_lines)
        assert all('\x1b' not in l for l in new_lines)

    def test_poller_reconnects_after_docker_error(self, app):
        """If Docker raises, the poller sleeps and retries (does not crash)."""
        from terraria_admin.extensions import console_buffer, console_lock

        call_count = {'n': 0}

        def fake_from_env():
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise Exception('Docker not available')
            # Second attempt succeeds but returns no lines
            client = MagicMock()
            client.containers.get.return_value = MagicMock(
                logs=MagicMock(return_value=iter([]))
            )
            return client

        done = threading.Event()
        sleep_count = {'n': 0}

        def fake_sleep(t):
            sleep_count['n'] += 1
            if sleep_count['n'] >= 2:
                done.set()
                raise SystemExit

        with patch('docker.from_env', side_effect=fake_from_env), \
             patch('terraria_admin.services.console.time.sleep', side_effect=fake_sleep):
            from terraria_admin.services.console import start_console_poller
            start_console_poller(app)
            done.wait(timeout=4)

        # Must have retried at least once after the initial failure
        assert call_count['n'] >= 2, 'poller must reconnect after Docker error'

    def test_poller_respects_max_console_lines(self, app):
        """Buffer must not exceed MAX_CONSOLE_LINES."""
        from terraria_admin.extensions import console_buffer, console_lock, MAX_CONSOLE_LINES

        # Flood with more lines than the limit
        overflow = MAX_CONSOLE_LINES + 50
        log_lines = [f'line {i}\n'.encode() for i in range(overflow)]

        mock_container = MagicMock()
        mock_container.logs.return_value = iter(log_lines)
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        done = threading.Event()

        def fake_sleep(t):
            done.set()
            raise SystemExit

        with console_lock:
            console_buffer.clear()

        with patch('docker.from_env', return_value=mock_client), \
             patch('terraria_admin.services.console.time.sleep', side_effect=fake_sleep):
            from terraria_admin.services.console import start_console_poller
            start_console_poller(app)
            done.wait(timeout=5)

        with console_lock:
            assert len(console_buffer) <= MAX_CONSOLE_LINES
