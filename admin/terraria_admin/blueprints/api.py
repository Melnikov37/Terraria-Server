import subprocess

from flask import Blueprint, current_app, jsonify, render_template, request

from ..decorators import login_required
from ..services.server import get_server_status, get_players
from ..services.mods import list_mods
from ..services.world import get_version_info

bp = Blueprint('api', __name__)


@bp.route('/logs')
@login_required
def logs():
    return render_template('logs.html')


@bp.route('/api/status')
@login_required
def api_status():
    cfg = current_app.terraria_config
    return jsonify(get_server_status(cfg))


@bp.route('/api/players')
@login_required
def api_players():
    cfg = current_app.terraria_config
    return jsonify(get_players(cfg))


@bp.route('/api/version')
@login_required
def api_version():
    cfg = current_app.terraria_config
    return jsonify(get_version_info(cfg))


@bp.route('/api/mods')
@login_required
def api_mods():
    cfg = current_app.terraria_config
    return jsonify(list_mods(cfg))


@bp.route('/api/logs')
@login_required
def api_logs():
    cfg = current_app.terraria_config
    lines = min(int(request.args.get('lines', 300)), 1000)
    level = request.args.get('level', 'all')

    log_lines = _read_logs(cfg, lines)

    if level == 'error':
        log_lines = [l for l in log_lines if any(
            kw in l.lower() for kw in ('error', 'exception', 'fail', 'fatal'))]
    elif level == 'warn':
        log_lines = [l for l in log_lines if any(
            kw in l.lower() for kw in ('warn', 'error', 'exception', 'fail', 'fatal'))]
    return jsonify({'lines': log_lines})


def _read_logs(cfg, lines):
    """Try log file → journalctl → console buffer, in that order."""
    # 1. Log file (works in Docker if volume-mounted)
    log_file = getattr(cfg, 'LOG_FILE', None)
    if log_file:
        try:
            with open(log_file) as f:
                return f.readlines()[-lines:]
        except Exception:
            pass

    # 2. journalctl (works on bare-metal with systemd)
    try:
        result = subprocess.run(
            ['journalctl', '-u', cfg.SERVICE_NAME, f'-n{lines}', '--no-pager', '--output=short-iso'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.splitlines()
    except Exception:
        pass

    # 3. In-memory console buffer (always available in Docker)
    from ..extensions import console_buffer
    return list(console_buffer)[-lines:]


@bp.route('/api/diag')
@login_required
def api_diag():
    """Diagnostic endpoint: Docker connection, container logs, worlds dir, config."""
    cfg = current_app.terraria_config
    result = {
        'docker': {'connected': False, 'error': None},
        'container': {'name': cfg.SERVER_CONTAINER, 'status': None, 'logs_last': []},
        'console_buffer': {'size': 0, 'last': []},
        'worlds': {'dir': cfg.WORLDS_DIR, 'exists': False, 'files': []},
        'serverconfig': {'exists': False, 'content': None},
    }

    # Docker
    try:
        import docker
        client = docker.from_env()
        result['docker']['connected'] = True
        try:
            container = client.containers.get(cfg.SERVER_CONTAINER)
            result['container']['status'] = container.status
            raw = container.logs(tail=50, stdout=True, stderr=True)
            lines = raw.decode('utf-8', errors='replace').splitlines()
            result['container']['logs_last'] = lines[-50:]
        except Exception as exc:
            result['container']['status'] = f'error: {exc}'
        finally:
            client.close()
    except Exception as exc:
        result['docker']['error'] = str(exc)

    # Console buffer
    from ..extensions import console_buffer, console_lock
    with console_lock:
        buf = list(console_buffer)
    result['console_buffer']['size'] = len(buf)
    result['console_buffer']['last'] = buf[-20:]

    # Worlds dir
    import os
    if os.path.isdir(cfg.WORLDS_DIR):
        result['worlds']['exists'] = True
        result['worlds']['files'] = sorted(os.listdir(cfg.WORLDS_DIR))

    # Serverconfig
    try:
        with open(cfg.CONFIG_FILE) as f:
            result['serverconfig']['exists'] = True
            result['serverconfig']['content'] = f.read()
    except Exception:
        pass

    return jsonify(result)


@bp.route('/api/metrics')
@login_required
def api_metrics():
    cfg = current_app.terraria_config
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(cfg.TERRARIA_DIR)
            disk_used  = round(disk.used  / (1024 ** 3), 2)
            disk_total = round(disk.total / (1024 ** 3), 2)
            disk_pct   = round(disk.percent, 1)
        except Exception:
            disk_used = disk_total = disk_pct = None

        server_cpu = server_ram_mb = None
        for proc in psutil.process_iter(['pid', 'cmdline', 'cpu_percent', 'memory_info']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'tModLoader' in cmdline or 'TerrariaServer' in cmdline:
                    server_cpu    = proc.cpu_percent()
                    server_ram_mb = round(proc.memory_info().rss / (1024 ** 2), 1)
                    break
            except Exception:
                pass

        return jsonify({
            'cpu_percent':  cpu,
            'ram_used_gb':  round(mem.used  / (1024 ** 3), 2),
            'ram_total_gb': round(mem.total / (1024 ** 3), 2),
            'ram_percent':  mem.percent,
            'disk_used_gb':  disk_used,
            'disk_total_gb': disk_total,
            'disk_percent':  disk_pct,
            'server_cpu':    server_cpu,
            'server_ram_mb': server_ram_mb,
        })
    except ImportError:
        return jsonify({'error': 'psutil not installed'})
    except Exception as exc:
        return jsonify({'error': str(exc)})
