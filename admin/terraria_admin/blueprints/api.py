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


@bp.route('/diag')
@login_required
def diag_page():
    return render_template('diag.html')


@bp.route('/api/diag')
@login_required
def api_diag():
    """Diagnostic endpoint: Docker connection, container exec probes, worlds dir, log file."""
    import os
    cfg = current_app.terraria_config
    result = {
        'docker': {'connected': False, 'error': None},
        'container': {
            'name': cfg.SERVER_CONTAINER,
            'status': None,
            'tty': None,
            'logs_last': [],
            'entrypoint_args_section': None,
            'wld_search': None,
            'terraria_ls': None,
            'tml_logs_ls': None,
            'log_file_tail': None,
        },
        'console_buffer': {'size': 0, 'last': []},
        'worlds': {'dir': cfg.WORLDS_DIR, 'exists': False, 'files': []},
        'serverconfig': {'exists': False, 'content': None},
        'log_file': {'path': getattr(cfg, 'LOG_FILE', None), 'exists': False, 'tail': []},
    }

    # Docker + container exec probes
    try:
        import docker
        client = docker.from_env()
        result['docker']['connected'] = True
        try:
            container = client.containers.get(cfg.SERVER_CONTAINER)
            result['container']['status'] = container.status
            result['container']['tty'] = container.attrs.get('Config', {}).get('Tty', False)

            # Docker logs (non-streaming) — may be empty if tModLoader writes to file
            raw = container.logs(tail=100, stdout=True, stderr=True)
            lines = raw.decode('utf-8', errors='replace').splitlines()
            result['container']['logs_last'] = [l for l in lines if l.strip()][-50:]

            if container.status == 'running':
                def _exec(sh_cmd):
                    """Run sh -c '...' inside the container."""
                    try:
                        r = container.exec_run(['sh', '-c', sh_cmd],
                                               stdout=True, stderr=True)
                        return r.output.decode('utf-8', errors='replace').strip()
                    except Exception as e:
                        return f'exec error: {e}'

                # Show ARGS section of entrypoint to verify worldpath fix is deployed
                result['container']['entrypoint_args_section'] = _exec(
                    'grep -n "ARGS\\|worldpath\\|SERVERCONFIG\\|config" /entrypoint.sh | head -20'
                )
                # Find .wld files anywhere in the container (most important!)
                result['container']['wld_search'] = _exec(
                    'find / -name "*.wld" -not -path "/proc/*" -not -path "/sys/*" 2>/dev/null || echo "(none found)"'
                )
                # List shared volume
                result['container']['terraria_ls'] = _exec('ls -lah /opt/terraria/')
                # List tModLoader log directory (reveals if logs are being written)
                result['container']['tml_logs_ls'] = _exec(
                    'ls -lah /root/.local/share/Terraria/tModLoader/Logs/ 2>/dev/null || echo "(dir not found)"'
                )
                # Last 30 lines of tModLoader server.log if it exists
                result['container']['log_file_tail'] = _exec(
                    'tail -30 /root/.local/share/Terraria/tModLoader/Logs/server.log 2>/dev/null || echo "(log not found)"'
                )
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

    # Log file (on shared volume after docker-compose mount)
    log_file = getattr(cfg, 'LOG_FILE', None)
    if log_file and os.path.exists(log_file):
        result['log_file']['exists'] = True
        try:
            with open(log_file, 'r', errors='replace') as f:
                lines = f.readlines()
            result['log_file']['tail'] = [l.rstrip() for l in lines[-50:]]
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
