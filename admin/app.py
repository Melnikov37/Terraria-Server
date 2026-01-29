#!/usr/bin/env python3
"""
Terraria Server Web Admin Panel
Full server management via TShock REST API
"""

import os
import subprocess
import functools
from pathlib import Path
from datetime import datetime

import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from dotenv import load_dotenv

# Load environment
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# Configuration
TERRARIA_DIR = os.environ.get('TERRARIA_DIR', '/opt/terraria')
REST_URL = os.environ.get('REST_URL', 'http://127.0.0.1:7878')
REST_TOKEN = os.environ.get('REST_TOKEN', '')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')
SERVER_TYPE = os.environ.get('SERVER_TYPE', 'tshock')
CONFIG_FILE = os.path.join(TERRARIA_DIR, 'serverconfig.txt')
TSHOCK_CONFIG = os.path.join(TERRARIA_DIR, 'tshock', 'config.json')
SERVICE_NAME = 'terraria'

def get_server_type():
    """Get current server type from file or env"""
    type_file = os.path.join(TERRARIA_DIR, '.server_type')
    if os.path.exists(type_file):
        with open(type_file) as f:
            return f.read().strip()
    return SERVER_TYPE


# ============== Auth ==============

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============== REST API Helpers ==============

def rest_call(endpoint, method='GET', data=None):
    """Call TShock REST API"""
    try:
        url = f"{REST_URL}{endpoint}"
        params = {'token': REST_TOKEN}

        if method == 'GET':
            if data:
                params.update(data)
            resp = requests.get(url, params=params, timeout=5)
        else:
            if data:
                params.update(data)
            resp = requests.post(url, data=params, timeout=5)

        return resp.json() if resp.text else {'status': resp.status_code}
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'error': 'Server offline or REST API disabled'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def get_server_status():
    """Get comprehensive server status"""
    server_type = get_server_type()

    # Check systemd service
    try:
        result = subprocess.run(
            ['/usr/bin/systemctl', 'is-active', SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        service_running = result.stdout.strip() == 'active'
    except:
        service_running = False

    # Get version from file
    version = 'unknown'
    version_file = os.path.join(TERRARIA_DIR, '.server_version')
    if os.path.exists(version_file):
        with open(version_file) as f:
            version = f.read().strip()

    # For TShock, try REST API
    if server_type == 'tshock':
        rest_status = rest_call('/v2/server/status')

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

    # For vanilla or if REST failed, just check service
    return {
        'online': service_running,
        'service': service_running,
        'server_type': server_type,
        'version': version,
        'port': 7777,
        'players': '?' if service_running else 0,
        'max_players': 8,
        'error': None if service_running else 'Server is stopped'
    }


def get_players():
    """Get online players list"""
    result = rest_call('/v2/players/list')
    if result.get('status') == '200':
        return result.get('players', [])
    return []


# ============== Routes ==============

@app.route('/')
@login_required
def dashboard():
    status = get_server_status()
    players = get_players() if status.get('online') else []
    return render_template('dashboard.html', status=status, players=players)


@app.route('/players')
@login_required
def players():
    player_list = get_players()
    # Get bans
    bans_result = rest_call('/v2/bans/list')
    bans = bans_result.get('bans', []) if bans_result.get('status') == '200' else []
    return render_template('players.html', players=player_list, bans=bans)


@app.route('/players/kick', methods=['POST'])
@login_required
def kick_player():
    player = request.form.get('player')
    reason = request.form.get('reason', 'Kicked by admin')
    result = rest_call('/v2/players/kick', 'POST', {'player': player, 'reason': reason})
    if result.get('status') == '200':
        flash(f'Kicked {player}', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown")}', 'error')
    return redirect(url_for('players'))


@app.route('/players/ban', methods=['POST'])
@login_required
def ban_player():
    player = request.form.get('player')
    reason = request.form.get('reason', 'Banned by admin')
    result = rest_call('/v2/bans/create', 'POST', {
        'name': player,
        'reason': reason,
        'type': 'name'
    })
    if result.get('status') == '200':
        flash(f'Banned {player}', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown")}', 'error')
    return redirect(url_for('players'))


@app.route('/players/unban', methods=['POST'])
@login_required
def unban_player():
    ban_id = request.form.get('id')
    result = rest_call('/v2/bans/destroy', 'POST', {'id': ban_id})
    if result.get('status') == '200':
        flash('Ban removed', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown")}', 'error')
    return redirect(url_for('players'))


@app.route('/world')
@login_required
def world():
    status = get_server_status()
    return render_template('world.html', status=status)


@app.route('/world/time', methods=['POST'])
@login_required
def set_time():
    time = request.form.get('time')  # day, night, noon, midnight, or number
    result = rest_call('/v3/world/time', 'POST', {'time': time})
    if result.get('status') == '200':
        flash(f'Time set to {time}', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown")}', 'error')
    return redirect(url_for('world'))


@app.route('/world/broadcast', methods=['POST'])
@login_required
def broadcast():
    message = request.form.get('message')
    result = rest_call('/v2/server/broadcast', 'POST', {'msg': message})
    if result.get('status') == '200':
        flash('Message sent', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown")}', 'error')
    return redirect(url_for('world'))


@app.route('/world/command', methods=['POST'])
@login_required
def run_command():
    cmd = request.form.get('command')
    if not cmd.startswith('/'):
        cmd = '/' + cmd
    result = rest_call('/v3/server/rawcmd', 'POST', {'cmd': cmd})
    if result.get('status') == '200':
        response = result.get('response', ['Command executed'])
        flash(' | '.join(response), 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown")}', 'error')
    return redirect(url_for('world'))


@app.route('/world/save', methods=['POST'])
@login_required
def save_world():
    result = rest_call('/v2/world/save', 'POST')
    if result.get('status') == '200':
        flash('World saved', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown")}', 'error')
    return redirect(url_for('world'))


@app.route('/world/butcher', methods=['POST'])
@login_required
def butcher():
    """Kill all NPCs"""
    result = rest_call('/v2/world/butcher', 'POST', {'killfriendly': 'false'})
    if result.get('status') == '200':
        flash(f'Killed {result.get("killedcount", 0)} mobs', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown")}', 'error')
    return redirect(url_for('world'))


@app.route('/config')
@login_required
def config():
    # Read serverconfig.txt
    server_config = {}
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    server_config[key.strip()] = value.strip()

    # Read tshock config
    tshock_config = {}
    if Path(TSHOCK_CONFIG).exists():
        import json
        with open(TSHOCK_CONFIG) as f:
            try:
                data = json.load(f)
                tshock_config = data.get('Settings', {})
            except:
                pass

    version_info = get_version_info()
    return render_template('config.html', server_config=server_config, tshock_config=tshock_config, version=version_info)


@app.route('/config/save', methods=['POST'])
@login_required
def save_config():
    # Save serverconfig.txt
    config_keys = ['worldname', 'maxplayers', 'port', 'password', 'difficulty', 'autocreate', 'motd']

    lines = ['# TShock Server Configuration', f'# Modified: {datetime.now().isoformat()}', '']
    lines.append(f"world={TERRARIA_DIR}/worlds/{request.form.get('worldname', 'world1')}.wld")
    lines.append(f"worldpath={TERRARIA_DIR}/worlds")

    for key in config_keys:
        value = request.form.get(key, '')
        if key != 'worldname':
            lines.append(f"{key}={value}")

    lines.extend(['secure=1', 'language=en-US', 'upnp=0', 'npcstream=60', 'priority=1'])

    try:
        with open(CONFIG_FILE, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        flash('Configuration saved. Restart server to apply changes.', 'success')
    except Exception as e:
        flash(f'Error saving config: {e}', 'error')

    return redirect(url_for('config'))


@app.route('/server/<action>', methods=['POST'])
@login_required
def server_control(action):
    """Start/stop/restart server via systemctl"""
    if action not in ('start', 'stop', 'restart'):
        flash('Invalid action', 'error')
        return redirect(url_for('dashboard'))

    try:
        # Use full paths and .service suffix for sudoers compatibility
        result = subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', action, f'{SERVICE_NAME}.service'],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PATH': '/usr/bin:/bin'}
        )
        if result.returncode == 0:
            flash(f'Server {action}ed', 'success')
        else:
            flash(f'Error: {result.stderr or result.stdout}', 'error')
    except Exception as e:
        flash(f'Error: {e}', 'error')

    return redirect(url_for('dashboard'))


# ============== Update ==============

def get_version_info():
    """Get current and latest server versions"""
    server_type = get_server_type()

    current = "unknown"
    version_file = os.path.join(TERRARIA_DIR, '.server_version')
    if os.path.exists(version_file):
        with open(version_file) as f:
            current = f.read().strip()

    latest = "unknown"
    try:
        if server_type == 'tshock':
            resp = requests.get('https://api.github.com/repos/Pryaxis/TShock/releases/latest', timeout=5)
            if resp.ok:
                latest = resp.json().get('tag_name', 'unknown')
        else:
            # For vanilla, check terraria.org
            resp = requests.get('https://terraria.org/api/get/dedicated-servers-names', timeout=5)
            if resp.ok:
                files = resp.json()
                if files:
                    # Extract version from filename like "terraria-server-1452.zip"
                    import re
                    match = re.search(r'(\d+)', files[0])
                    if match:
                        ver = match.group(1)
                        latest = f"1.4.5.{ver[-1]}" if len(ver) == 4 else ver
    except:
        pass

    return {
        'current': current,
        'latest': latest,
        'server_type': server_type,
        'update_available': current != latest and latest != 'unknown'
    }


@app.route('/update', methods=['POST'])
@login_required
def update_server():
    """Run update script"""
    update_script = os.path.join(TERRARIA_DIR, 'update.sh')
    if not os.path.exists(update_script):
        flash('Update script not found', 'error')
        return redirect(url_for('config'))

    try:
        result = subprocess.run(
            ['/bin/bash', update_script],
            capture_output=True, text=True, timeout=300,
            cwd=TERRARIA_DIR
        )
        if result.returncode == 0:
            flash('Update completed successfully!', 'success')
        else:
            flash(f'Update failed: {result.stderr or result.stdout}', 'error')
    except subprocess.TimeoutExpired:
        flash('Update timed out', 'error')
    except Exception as e:
        flash(f'Update error: {e}', 'error')

    return redirect(url_for('config'))


# ============== API Endpoints ==============

@app.route('/api/status')
@login_required
def api_status():
    return jsonify(get_server_status())


@app.route('/api/players')
@login_required
def api_players():
    return jsonify(get_players())


@app.route('/api/version')
@login_required
def api_version():
    return jsonify(get_version_info())


# ============== Main ==============

if __name__ == '__main__':
    print("=" * 50)
    print("Terraria Web Admin Panel")
    print("=" * 50)
    print(f"Server directory: {TERRARIA_DIR}")
    print(f"REST API: {REST_URL}")
    print(f"Access: http://0.0.0.0:5000")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5000, debug=False)
