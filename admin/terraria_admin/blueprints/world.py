import os
import shutil
import subprocess
import time
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..decorators import login_required
from ..services.server import get_server_status, get_server_type
from ..services.tshock import rest_call
from ..services.screen import screen_send
from ..services.world import list_worlds

bp = Blueprint('world', __name__)


@bp.route('/world')
@login_required
def world():
    cfg = current_app.terraria_config
    status = get_server_status(cfg)
    worlds = list_worlds(cfg)
    return render_template('world.html', status=status, worlds=worlds)


@bp.route('/world/time', methods=['POST'])
@login_required
def set_time():
    cfg = current_app.terraria_config
    time_val = request.form.get('time')
    server_type = get_server_type(cfg)

    if server_type == 'tshock':
        result = rest_call('/v3/world/time', cfg, 'POST', {'time': time_val})
        if result.get('status') == '200':
            flash(f'Time set to {time_val}', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        tml_map = {'day': 'dawn', 'noon': 'noon', 'night': 'dusk', 'midnight': 'midnight'}
        cmd = tml_map.get(time_val, time_val)
        screen_send(cmd, cfg)
        flash(f'Time command "{cmd}" sent', 'success')

    return redirect(url_for('world.world'))


@bp.route('/world/broadcast', methods=['POST'])
@login_required
def broadcast():
    cfg = current_app.terraria_config
    message = request.form.get('message', '').strip()
    if not message:
        flash('Message cannot be empty', 'error')
        return redirect(url_for('world.world'))

    server_type = get_server_type(cfg)
    if server_type == 'tshock':
        result = rest_call('/v2/server/broadcast', cfg, 'POST', {'msg': message})
        if result.get('status') == '200':
            flash('Message sent', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send(f'say {message}', cfg)
        flash('Message sent', 'success')

    return redirect(url_for('world.world'))


@bp.route('/world/command', methods=['POST'])
@login_required
def run_command():
    cfg = current_app.terraria_config
    cmd = request.form.get('command', '').strip()
    if not cmd:
        flash('Command cannot be empty', 'error')
        return redirect(url_for('world.world'))

    server_type = get_server_type(cfg)
    if server_type == 'tshock':
        if not cmd.startswith('/'):
            cmd = '/' + cmd
        result = rest_call('/v3/server/rawcmd', cfg, 'POST', {'cmd': cmd})
        if result.get('status') == '200':
            response = result.get('response', ['Command executed'])
            flash(' | '.join(response), 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send(cmd, cfg)
        flash(f'Command "{cmd}" sent to server', 'success')

    return redirect(url_for('world.world'))


@bp.route('/world/save', methods=['POST'])
@login_required
def save_world():
    cfg = current_app.terraria_config
    server_type = get_server_type(cfg)
    if server_type == 'tshock':
        result = rest_call('/v2/world/save', cfg, 'POST')
        if result.get('status') == '200':
            flash('World saved', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send('save', cfg)
        flash('Save command sent', 'success')
    return redirect(url_for('world.world'))


@bp.route('/world/butcher', methods=['POST'])
@login_required
def butcher():
    cfg = current_app.terraria_config
    if get_server_type(cfg) == 'tshock':
        result = rest_call('/v2/world/butcher', cfg, 'POST', {'killfriendly': 'false'})
        if result.get('status') == '200':
            flash(f'Killed {result.get("killedcount", 0)} mobs', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        flash('Butcher is only available for TShock servers', 'error')
    return redirect(url_for('world.world'))


@bp.route('/world/recreate', methods=['POST'])
@login_required
def recreate_world():
    cfg = current_app.terraria_config
    worldname  = request.form.get('worldname', 'World')
    size       = request.form.get('size', '2')
    difficulty = request.form.get('difficulty', '0')

    try:
        subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', 'stop', 'terraria.service'],
            capture_output=True, timeout=30
        )
        time.sleep(3)

        worlds_dir = cfg.WORLDS_DIR
        backup_dir = os.path.join(
            cfg.TERRARIA_DIR, 'backups', datetime.now().strftime('%Y%m%d_%H%M%S')
        )
        os.makedirs(backup_dir, exist_ok=True)

        for fname in os.listdir(worlds_dir):
            src = os.path.join(worlds_dir, fname)
            dst = os.path.join(backup_dir, fname)
            if os.path.isfile(src):
                shutil.move(src, dst)

        config_lines = [
            '# Terraria Server Configuration',
            f'# Recreated: {datetime.now().isoformat()}',
            '',
            f'world={cfg.TERRARIA_DIR}/worlds/{worldname}.wld',
            f'autocreate={size}',
            f'worldname={worldname}',
            f'difficulty={difficulty}',
            f'worldpath={cfg.TERRARIA_DIR}/worlds',
            'maxplayers=8',
            'port=7777',
            'password=',
            'motd=',
            'secure=1',
            'language=en-US',
            'upnp=0',
            'npcstream=60',
            'priority=1',
        ]
        with open(cfg.CONFIG_FILE, 'w') as f:
            f.write('\n'.join(config_lines) + '\n')

        subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', 'start', 'terraria.service'],
            capture_output=True, timeout=30
        )
        flash(f'World "{worldname}" will be created on server start. Old world backed up.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')

    return redirect(url_for('world.world'))


@bp.route('/world/switch', methods=['POST'])
@login_required
def world_switch():
    cfg = current_app.terraria_config
    world_name = request.form.get('world_name', '').strip()
    if not world_name or os.sep in world_name or '..' in world_name:
        flash('Invalid world name', 'error')
        return redirect(url_for('world.world'))

    world_file = os.path.join(cfg.WORLDS_DIR, world_name + '.wld')
    if not os.path.exists(world_file):
        flash(f'World file not found: {world_name}.wld', 'error')
        return redirect(url_for('world.world'))

    config = {}
    if os.path.exists(cfg.CONFIG_FILE):
        with open(cfg.CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    config[k.strip()] = v.strip()

    config['world'] = world_file
    config['worldname'] = world_name
    config.pop('autocreate', None)

    lines = ['# Terraria Server Configuration', f'# World switched: {datetime.now().isoformat()}', '']
    for k, v in config.items():
        lines.append(f'{k}={v}')

    try:
        with open(cfg.CONFIG_FILE, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', 'restart', 'terraria.service'],
            capture_output=True, timeout=30
        )
        flash(f'Switched to world "{world_name}". Server restarting\u2026', 'success')
    except Exception as exc:
        flash(f'Error: {exc}', 'error')

    return redirect(url_for('world.world'))
