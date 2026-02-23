import os
import shutil
import time
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..decorators import login_required
from ..services.server import get_server_status, get_server_type, container_action, read_serverconfig
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
    # Detect world generation in progress: server is running, no .wld files yet,
    # but serverconfig has autocreate set — tModLoader is generating the world.
    generating = None
    if not worlds and status.get('online'):
        worldname = read_serverconfig('worldname', cfg)
        autocreate = read_serverconfig('autocreate', cfg)
        if worldname and autocreate:
            generating = worldname
    return render_template('world.html', status=status, worlds=worlds, generating=generating)


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
    message = request.form.get('message', '').strip()[:500]
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
    cmd = request.form.get('command', '').strip()[:500]
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
    worldname  = os.path.basename(request.form.get('worldname', 'World').strip()).replace('..', '').strip()[:64] or 'World'
    size       = request.form.get('size', '2') if request.form.get('size') in ('1', '2', '3') else '2'
    difficulty = request.form.get('difficulty', '0') if request.form.get('difficulty') in ('0', '1', '2', '3') else '0'
    evil       = request.form.get('evil', '0') if request.form.get('evil') in ('0', '1', '2') else '0'
    seed       = request.form.get('seed', '').strip()

    world_file = os.path.join(cfg.WORLDS_DIR, worldname + '.wld')
    if os.path.exists(world_file):
        flash(f'World "{worldname}" already exists. Use Switch and Restart to load it, or choose a different name.', 'error')
        return redirect(url_for('world.world'))

    try:
        try:
            container_action('stop', cfg)
        except Exception:
            pass
        time.sleep(3)

        os.makedirs(cfg.WORLDS_DIR, exist_ok=True)
        config_lines = [
            '# Terraria Server Configuration',
            f'# Created: {datetime.now().isoformat()}',
            '',
            f'world={cfg.TERRARIA_DIR}/worlds/{worldname}.wld',
            f'autocreate={size}',
            f'worldname={worldname}',
            f'difficulty={difficulty}',
            f'evil={evil}',
            *([f'seed={seed}'] if seed else []),
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

        try:
            container_action('start', cfg)
        except Exception:
            pass
        flash(f'World "{worldname}" is being generated. Server restarting…', 'success')
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
        try:
            container_action('restart', cfg)
        except Exception:
            pass
        flash(f'Switched to world "{world_name}". Server restarting…', 'success')
    except Exception as exc:
        flash(f'Error: {exc}', 'error')

    return redirect(url_for('world.world'))
