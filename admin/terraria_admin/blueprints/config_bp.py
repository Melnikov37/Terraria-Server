import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..decorators import login_required
from ..services.server import get_server_type
from ..services.world import get_version_info, update_tmodloader
from ..services.discord import get_discord_config, save_discord_config, discord_notify

bp = Blueprint('config_bp', __name__)


@bp.route('/config')
@login_required
def config():
    cfg = current_app.terraria_config
    server_config = {}
    if Path(cfg.CONFIG_FILE).exists():
        with open(cfg.CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    server_config[key.strip()] = value.strip()

    tshock_config = {}
    if Path(cfg.TSHOCK_CONFIG).exists():
        with open(cfg.TSHOCK_CONFIG) as f:
            try:
                data = json.load(f)
                tshock_config = data.get('Settings', {})
            except Exception:
                pass

    version_info = get_version_info(cfg)
    server_type = get_server_type(cfg)
    return render_template(
        'config.html',
        server_config=server_config,
        tshock_config=tshock_config,
        version=version_info,
        server_type=server_type,
        discord_config=get_discord_config(cfg),
    )


@bp.route('/config/save', methods=['POST'])
@login_required
def save_config():
    cfg = current_app.terraria_config
    config_keys = ['worldname', 'maxplayers', 'port', 'password', 'difficulty', 'autocreate', 'motd']

    lines = ['# Terraria Server Configuration', f'# Modified: {datetime.now().isoformat()}', '']
    lines.append(f"world={cfg.TERRARIA_DIR}/worlds/{request.form.get('worldname', 'world1')}.wld")
    lines.append(f"worldpath={cfg.TERRARIA_DIR}/worlds")

    for key in config_keys:
        value = request.form.get(key, '')
        if key != 'worldname':
            lines.append(f"{key}={value}")

    lines.extend(['secure=1', 'language=en-US', 'upnp=0', 'npcstream=60', 'priority=1'])

    try:
        with open(cfg.CONFIG_FILE, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        flash('Configuration saved. Restart server to apply changes.', 'success')
    except Exception as e:
        flash(f'Error saving config: {e}', 'error')

    return redirect(url_for('config_bp.config'))


@bp.route('/update', methods=['POST'])
@login_required
def update_server():
    cfg = current_app.terraria_config
    update_script = os.path.join(cfg.TERRARIA_DIR, 'update.sh')
    if not os.path.exists(update_script):
        flash('Update script not found', 'error')
        return redirect(url_for('config_bp.config'))

    try:
        result = subprocess.run(
            ['/bin/bash', update_script],
            capture_output=True, text=True, timeout=300,
            cwd=cfg.TERRARIA_DIR
        )
        if result.returncode == 0:
            flash('Update completed successfully!', 'success')
        else:
            flash(f'Update failed: {result.stderr or result.stdout}', 'error')
    except subprocess.TimeoutExpired:
        flash('Update timed out', 'error')
    except Exception as e:
        flash(f'Update error: {e}', 'error')

    return redirect(url_for('config_bp.config'))


@bp.route('/update/tmodloader', methods=['POST'])
@login_required
def update_tmodloader_route():
    cfg = current_app.terraria_config
    ok, msg = update_tmodloader(cfg)
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('config_bp.config'))


@bp.route('/discord/config', methods=['POST'])
@login_required
def discord_config_save():
    cfg = current_app.terraria_config
    dcfg = {
        'webhook_url':        request.form.get('webhook_url', '').strip(),
        'notify_start':       'notify_start'       in request.form,
        'notify_stop':        'notify_stop'        in request.form,
        'notify_join':        'notify_join'        in request.form,
        'notify_leave':       'notify_leave'       in request.form,
        'notify_backup':      'notify_backup'      in request.form,
        'notify_mod_install': 'notify_mod_install' in request.form,
    }
    save_discord_config(dcfg, cfg)
    flash('Discord settings saved.', 'success')
    return redirect(url_for('config_bp.config'))


@bp.route('/discord/test', methods=['POST'])
@login_required
def discord_test():
    cfg = current_app.terraria_config
    dcfg = get_discord_config(cfg)
    if not dcfg.get('webhook_url', '').strip():
        flash('No webhook URL configured.', 'error')
        return redirect(url_for('config_bp.config'))
    discord_notify(
        ':bell: Test notification from **Terraria Admin Panel**',
        cfg, color=0x58a6ff, event='info'
    )
    flash('Test notification sent (if webhook URL is valid).', 'success')
    return redirect(url_for('config_bp.config'))
