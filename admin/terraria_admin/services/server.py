import os
import subprocess

from .tshock import rest_call
from .screen import is_screen_running, screen_cmd_output


def get_server_type(cfg):
    type_file = os.path.join(cfg.TERRARIA_DIR, '.server_type')
    if os.path.exists(type_file):
        with open(type_file) as f:
            return f.read().strip()
    return cfg.SERVER_TYPE


def _service_active(cfg):
    try:
        result = subprocess.run(
            ['/usr/bin/systemctl', 'is-active', cfg.SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == 'active'
    except Exception:
        return False


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
        screen_active = service_running and is_screen_running(cfg)
        return {
            'online': screen_active,
            'service': service_running,
            'server_type': server_type,
            'version': version,
            'port': int(read_serverconfig('port', cfg) or 7777),
            'players': '?',
            'max_players': int(read_serverconfig('maxplayers', cfg) or 8),
            'world': read_serverconfig('worldname', cfg) or 'Unknown',
        }

    return {
        'online': service_running,
        'service': service_running,
        'server_type': server_type,
        'version': version,
        'port': int(read_serverconfig('port', cfg) or 7777),
        'players': '?' if service_running else 0,
        'max_players': int(read_serverconfig('maxplayers', cfg) or 8),
        'world': read_serverconfig('worldname', cfg) or 'Unknown',
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
