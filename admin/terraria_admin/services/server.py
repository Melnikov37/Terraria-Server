import os
import time

from .tshock import rest_call
from .screen import is_screen_running, screen_cmd_output

# Cache container status for 5 seconds to reduce Docker SDK connections
_status_cache: dict = {}
_STATUS_CACHE_TTL = 5


def get_server_type(cfg):
    type_file = os.path.join(cfg.TERRARIA_DIR, '.server_type')
    if os.path.exists(type_file):
        with open(type_file) as f:
            return f.read().strip()
    return cfg.SERVER_TYPE


def _service_active(cfg):
    """Return True if the terraria server Docker container is running.

    Caches the result for _STATUS_CACHE_TTL seconds to limit Docker SDK
    connections when multiple pages poll /api/status frequently.
    Also caches StartedAt so _container_uptime() can compute uptime without
    an extra Docker call.
    """
    import docker
    cache_key = cfg.SERVER_CONTAINER
    cached = _status_cache.get(cache_key)
    if cached and (time.monotonic() - cached['ts']) < _STATUS_CACHE_TTL:
        return cached['running']
    client = docker.from_env()
    try:
        container = client.containers.get(cfg.SERVER_CONTAINER)
        running = container.status == 'running'
        started_at = container.attrs.get('State', {}).get('StartedAt', '') if running else ''
    except Exception:
        running = False
        started_at = ''
    finally:
        client.close()
    _status_cache[cache_key] = {'running': running, 'started_at': started_at, 'ts': time.monotonic()}
    return running


def _container_uptime(cfg):
    """Return a human-readable uptime string derived from the cached container StartedAt.

    Requires _service_active() to have been called first (it populates the cache).
    Returns '' when the container is not running or start time is unavailable.
    """
    from datetime import datetime, timezone
    cached = _status_cache.get(cfg.SERVER_CONTAINER)
    started_at = (cached or {}).get('started_at', '')
    if not started_at:
        return ''
    try:
        # Docker uses RFC3339 nanoseconds: "2024-01-15T10:30:00.123456789Z"
        # Python's fromisoformat only handles up to microseconds — truncate.
        ts = started_at[:26].rstrip('Z') + '+00:00'
        start = datetime.fromisoformat(ts)
        total = int((datetime.now(timezone.utc) - start).total_seconds())
        if total < 0:
            return ''
        h, rem = divmod(total, 3600)
        m, s   = divmod(rem, 60)
        if h >= 24:
            d, h = divmod(h, 24)
            return f'{d}d {h}h {m}m'
        return f'{h:02d}:{m:02d}:{s:02d}'
    except Exception:
        return ''


def container_action(action, cfg):
    """Start, stop, or restart the terraria server container via Docker SDK."""
    import docker
    client = docker.from_env()
    try:
        container = client.containers.get(cfg.SERVER_CONTAINER)
        if action == 'stop':
            container.stop(timeout=30)
        elif action == 'start':
            container.start()
        elif action == 'restart':
            container.restart(timeout=30)
    finally:
        client.close()


def _stored_version(cfg):
    version_file = os.path.join(cfg.TERRARIA_DIR, '.server_version')
    if os.path.exists(version_file):
        with open(version_file) as f:
            return f.read().strip()
    return 'unknown'


def read_serverconfig(key, cfg):
    """Read a single key from serverconfig.txt."""
    try:
        with open(cfg.CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f'{key}='):
                    return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return None


def get_server_status(cfg):
    server_type = get_server_type(cfg)
    service_running = _service_active(cfg)
    version = _stored_version(cfg)

    if server_type == 'tshock':
        rest_status = rest_call('/v2/server/status', cfg)
        if rest_status.get('status') == '200':
            return {
                'online': True,
                'service': service_running,
                'server_type': server_type,
                'name': rest_status.get('name', 'Terraria Server'),
                'port': rest_status.get('port', 7777),
                'players': rest_status.get('playercount', 0),
                'max_players': rest_status.get('maxplayers', 8),
                'world': rest_status.get('world', 'Unknown'),
                'uptime': rest_status.get('uptime', ''),
                'version': rest_status.get('serverversion', version),
            }

    if server_type == 'tmodloader':
        return {
            'online': service_running,
            'service': service_running,
            'server_type': server_type,
            'version': version,
            'port': int(read_serverconfig('port', cfg) or 7777),
            'players': None,
            'max_players': int(read_serverconfig('maxplayers', cfg) or 8),
            'world': read_serverconfig('worldname', cfg) or 'Unknown',
            'uptime': _container_uptime(cfg),
        }

    return {
        'online': service_running,
        'service': service_running,
        'server_type': server_type,
        'version': version,
        'port': int(read_serverconfig('port', cfg) or 7777),
        'players': None,
        'max_players': int(read_serverconfig('maxplayers', cfg) or 8),
        'world': read_serverconfig('worldname', cfg) or 'Unknown',
        'uptime': _container_uptime(cfg),
        'error': None if service_running else 'Server is stopped',
    }


def get_players(cfg):
    """Return list of online players as [{'nickname': str}]."""
    server_type = get_server_type(cfg)

    if server_type == 'tshock':
        result = rest_call('/v2/players/list', cfg)
        if result.get('status') == '200':
            return result.get('players', [])
        return []

    if server_type == 'tmodloader':
        output = screen_cmd_output('players', cfg, wait=0.8)
        players = []
        in_list = False
        for line in output.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(':') and len(stripped) > 2:
                name = stripped[1:].strip()
                if name:
                    players.append({'nickname': name})
                in_list = True
            elif in_list and stripped and not any(
                c in stripped for c in [':', '[', ']', '>', '<']
            ):
                players.append({'nickname': stripped})
        return players

    return []
