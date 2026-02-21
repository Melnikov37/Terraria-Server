#!/usr/bin/env python3
"""
Terraria Server Web Admin Panel
Supports TShock (REST API), Vanilla, and tModLoader (screen-based communication)
"""

import os
import json
import subprocess
import functools
import time
import shutil
import tempfile
import zlib
from pathlib import Path
from datetime import datetime

import requests
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, session
)
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256 MB max upload

# Configuration
TERRARIA_DIR   = os.environ.get('TERRARIA_DIR', '/opt/terraria')
REST_URL       = os.environ.get('REST_URL', 'http://127.0.0.1:7878')
REST_TOKEN     = os.environ.get('REST_TOKEN', '')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')
SERVER_TYPE    = os.environ.get('SERVER_TYPE', 'tshock')
SCREEN_SESSION  = os.environ.get('SCREEN_SESSION', 'terraria')
MODS_DIR        = os.environ.get('MODS_DIR', '/opt/terraria/.local/share/Terraria/tModLoader/Mods')
STEAMCMD_BIN    = os.environ.get('STEAMCMD_BIN', '/opt/steamcmd/steamcmd.sh')
TERRARIA_APP_ID = '1281930'

# Known Workshop IDs for popular mods — used for auto-installing dependencies.
# Keys are tModLoader internal mod names (as they appear in modReferences / .tmod filenames).
KNOWN_WORKSHOP_IDS = {
    'CalamityMod':          '2824688072',
    'CalamityModMusic':     '2824688266',
    'ThoriumMod':           '2756794847',
    'BossChecklist':        '2756794864',
    'RecipeBrowser':        '2756794983',
    'MagicStorage':         '2563309347',
    'Census':               '2687356363',
    'AlchemistNPCLite':     '2382561813',
    'ImprovedTorches':      '2790887285',
    'HERO_Mod':             '2564599814',
    'WingSlot':             '2563309386',
    'CheatSheet':           '2563309402',
    'AutoTrash':            '2563372007',
    'Fargo_Mutant_Mod':     '2563309826',
    'FargowiltasSouls':     '2564815791',
    'StarlightRiver':       '2609329524',
    'Infernum':             '3142790752',
    'Terraria_Overhaul':    '1417245098',
    'MusicBox':             '2563309347',
    'HEROsMod':             '2564599814',
    'FancyLighting':        '2907538845',
    'SpiritMod':            '2563309339',
    'Redemption':           '2610690817',
    'GRealm':               '2563309387',
    'AssortedCrazyThings':  '2563309359',
    'Wikithis':             '2563309402',
    'AmuletOfManyMinions':  '2398614480',
}
CONFIG_FILE    = os.path.join(TERRARIA_DIR, 'serverconfig.txt')
TSHOCK_CONFIG  = os.path.join(TERRARIA_DIR, 'tshock', 'config.json')
SERVICE_NAME   = 'terraria'


def get_server_type():
    type_file = os.path.join(TERRARIA_DIR, '.server_type')
    if os.path.exists(type_file):
        with open(type_file) as f:
            return f.read().strip()
    return SERVER_TYPE


# ============================================================
# Auth
# ============================================================

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


# ============================================================
# TShock REST API helpers
# ============================================================

def rest_call(endpoint, method='GET', data=None):
    """Call TShock REST API. Only used when server_type == tshock."""
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


# ============================================================
# tModLoader screen-based communication helpers
# ============================================================

def screen_send(cmd):
    """Send a command to the tModLoader server via screen."""
    try:
        subprocess.run(
            ['screen', '-S', SCREEN_SESSION, '-X', 'stuff', f'{cmd}\r'],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        return False


def screen_capture(wait=0.6):
    """Read current screen terminal contents."""
    try:
        tmpfile = tempfile.mktemp(suffix='.txt', prefix='tserver_')
        time.sleep(wait)
        subprocess.run(
            ['screen', '-S', SCREEN_SESSION, '-p', '0', '-X', 'hardcopy', '-h', tmpfile],
            capture_output=True, timeout=5
        )
        if os.path.exists(tmpfile):
            with open(tmpfile, 'r', errors='ignore') as f:
                content = f.read()
            try:
                os.unlink(tmpfile)
            except OSError:
                pass
            return content
    except Exception:
        pass
    return ''


def is_screen_running():
    """Check whether a screen session named SCREEN_SESSION exists."""
    try:
        result = subprocess.run(
            ['screen', '-ls'], capture_output=True, text=True, timeout=5
        )
        return SCREEN_SESSION in result.stdout
    except Exception:
        return False


def screen_cmd_output(cmd, wait=0.8):
    """
    Send cmd, wait, return last 60 lines of screen output.
    Used for commands that produce a response (e.g. 'players').
    """
    screen_send(cmd)
    return screen_capture(wait=wait)


# ============================================================
# Server status helpers
# ============================================================

def _service_active():
    try:
        result = subprocess.run(
            ['/usr/bin/systemctl', 'is-active', SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == 'active'
    except Exception:
        return False


def _stored_version():
    version_file = os.path.join(TERRARIA_DIR, '.server_version')
    if os.path.exists(version_file):
        with open(version_file) as f:
            return f.read().strip()
    return 'unknown'


def _read_serverconfig(key):
    """Read a single key from serverconfig.txt."""
    try:
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f'{key}='):
                    return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return None


def get_server_status():
    server_type = get_server_type()
    service_running = _service_active()
    version = _stored_version()

    # TShock — use REST API
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

    # tModLoader — check screen session
    if server_type == 'tmodloader':
        screen_active = service_running and is_screen_running()
        return {
            'online': screen_active,
            'service': service_running,
            'server_type': server_type,
            'version': version,
            'port': int(_read_serverconfig('port') or 7777),
            'players': '?',
            'max_players': int(_read_serverconfig('maxplayers') or 8),
            'world': _read_serverconfig('worldname') or 'Unknown',
        }

    # Vanilla
    return {
        'online': service_running,
        'service': service_running,
        'server_type': server_type,
        'version': version,
        'port': int(_read_serverconfig('port') or 7777),
        'players': '?' if service_running else 0,
        'max_players': int(_read_serverconfig('maxplayers') or 8),
        'world': _read_serverconfig('worldname') or 'Unknown',
        'error': None if service_running else 'Server is stopped',
    }


def get_players():
    """Return list of online players as [{'nickname': str}]."""
    server_type = get_server_type()

    if server_type == 'tshock':
        result = rest_call('/v2/players/list')
        if result.get('status') == '200':
            return result.get('players', [])
        return []

    if server_type == 'tmodloader':
        output = screen_cmd_output('players', wait=0.8)
        players = []
        lines = output.split('\n')
        # Parse tModLoader player list output.
        # Typical format: ": PlayerName" or "PlayerName is playing."
        in_list = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # tML prints ":" prefix for each player, or just the name
            if stripped.startswith(':') and len(stripped) > 2:
                name = stripped[1:].strip()
                if name:
                    players.append({'nickname': name})
                in_list = True
            elif in_list and stripped and not any(
                c in stripped for c in [':', '[', ']', '>', '<']
            ):
                # Sometimes players are listed without prefix after the header
                players.append({'nickname': stripped})

        return players

    return []


# ============================================================
# Routes — Dashboard
# ============================================================

@app.route('/')
@login_required
def dashboard():
    status = get_server_status()
    players = get_players() if status.get('online') else []
    return render_template('dashboard.html', status=status, players=players)


# ============================================================
# Routes — Server control
# ============================================================

@app.route('/server/<action>', methods=['POST'])
@login_required
def server_control(action):
    if action not in ('start', 'stop', 'restart'):
        flash('Invalid action', 'error')
        return redirect(url_for('dashboard'))

    try:
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


# ============================================================
# Routes — Players
# ============================================================

@app.route('/players')
@login_required
def players():
    player_list = get_players()
    bans = []
    if get_server_type() == 'tshock':
        bans_result = rest_call('/v2/bans/list')
        bans = bans_result.get('bans', []) if bans_result.get('status') == '200' else []
    return render_template('players.html', players=player_list, bans=bans)


@app.route('/players/kick', methods=['POST'])
@login_required
def kick_player():
    player = request.form.get('player', '').strip()
    reason = request.form.get('reason', 'Kicked by admin')
    if not player:
        flash('Player name is required', 'error')
        return redirect(url_for('players'))

    server_type = get_server_type()
    if server_type == 'tshock':
        result = rest_call('/v2/players/kick', 'POST', {'player': player, 'reason': reason})
        if result.get('status') == '200':
            flash(f'Kicked {player}', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send(f'kick {player}')
        flash(f'Kick command sent for {player}', 'success')

    return redirect(url_for('players'))


@app.route('/players/ban', methods=['POST'])
@login_required
def ban_player():
    player = request.form.get('player', '').strip()
    reason = request.form.get('reason', 'Banned by admin')
    if not player:
        flash('Player name is required', 'error')
        return redirect(url_for('players'))

    server_type = get_server_type()
    if server_type == 'tshock':
        result = rest_call('/v2/bans/create', 'POST', {
            'name': player, 'reason': reason, 'type': 'name'
        })
        if result.get('status') == '200':
            flash(f'Banned {player}', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send(f'ban {player}')
        flash(f'Ban command sent for {player}', 'success')

    return redirect(url_for('players'))


@app.route('/players/unban', methods=['POST'])
@login_required
def unban_player():
    ban_id = request.form.get('id')
    if get_server_type() == 'tshock':
        result = rest_call('/v2/bans/destroy', 'POST', {'id': ban_id})
        if result.get('status') == '200':
            flash('Ban removed', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        flash('Unban via ID is only available for TShock servers', 'error')
    return redirect(url_for('players'))


# ============================================================
# Routes — World
# ============================================================

@app.route('/world')
@login_required
def world():
    status = get_server_status()
    return render_template('world.html', status=status)


@app.route('/world/time', methods=['POST'])
@login_required
def set_time():
    time_val = request.form.get('time')
    server_type = get_server_type()

    if server_type == 'tshock':
        result = rest_call('/v3/world/time', 'POST', {'time': time_val})
        if result.get('status') == '200':
            flash(f'Time set to {time_val}', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        # tModLoader accepts: dawn, noon, dusk, midnight
        tml_map = {'day': 'dawn', 'noon': 'noon', 'night': 'dusk', 'midnight': 'midnight'}
        cmd = tml_map.get(time_val, time_val)
        screen_send(cmd)
        flash(f'Time command "{cmd}" sent', 'success')

    return redirect(url_for('world'))


@app.route('/world/broadcast', methods=['POST'])
@login_required
def broadcast():
    message = request.form.get('message', '').strip()
    if not message:
        flash('Message cannot be empty', 'error')
        return redirect(url_for('world'))

    server_type = get_server_type()
    if server_type == 'tshock':
        result = rest_call('/v2/server/broadcast', 'POST', {'msg': message})
        if result.get('status') == '200':
            flash('Message sent', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send(f'say {message}')
        flash('Message sent', 'success')

    return redirect(url_for('world'))


@app.route('/world/command', methods=['POST'])
@login_required
def run_command():
    cmd = request.form.get('command', '').strip()
    if not cmd:
        flash('Command cannot be empty', 'error')
        return redirect(url_for('world'))

    server_type = get_server_type()
    if server_type == 'tshock':
        if not cmd.startswith('/'):
            cmd = '/' + cmd
        result = rest_call('/v3/server/rawcmd', 'POST', {'cmd': cmd})
        if result.get('status') == '200':
            response = result.get('response', ['Command executed'])
            flash(' | '.join(response), 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send(cmd)
        flash(f'Command "{cmd}" sent to server', 'success')

    return redirect(url_for('world'))


@app.route('/world/save', methods=['POST'])
@login_required
def save_world():
    server_type = get_server_type()
    if server_type == 'tshock':
        result = rest_call('/v2/world/save', 'POST')
        if result.get('status') == '200':
            flash('World saved', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send('save')
        flash('Save command sent', 'success')
    return redirect(url_for('world'))


@app.route('/world/butcher', methods=['POST'])
@login_required
def butcher():
    if get_server_type() == 'tshock':
        result = rest_call('/v2/world/butcher', 'POST', {'killfriendly': 'false'})
        if result.get('status') == '200':
            flash(f'Killed {result.get("killedcount", 0)} mobs', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        flash('Butcher is only available for TShock servers', 'error')
    return redirect(url_for('world'))


@app.route('/world/recreate', methods=['POST'])
@login_required
def recreate_world():
    worldname = request.form.get('worldname', 'World')
    size = request.form.get('size', '2')
    difficulty = request.form.get('difficulty', '0')

    try:
        subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', 'stop', 'terraria.service'],
            capture_output=True, timeout=30
        )
        time.sleep(3)

        worlds_dir = os.path.join(TERRARIA_DIR, 'worlds')
        backup_dir = os.path.join(TERRARIA_DIR, 'backups', datetime.now().strftime('%Y%m%d_%H%M%S'))
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
            f'world={TERRARIA_DIR}/worlds/{worldname}.wld',
            f'autocreate={size}',
            f'worldname={worldname}',
            f'difficulty={difficulty}',
            f'worldpath={TERRARIA_DIR}/worlds',
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
        with open(CONFIG_FILE, 'w') as f:
            f.write('\n'.join(config_lines) + '\n')

        subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', 'start', 'terraria.service'],
            capture_output=True, timeout=30
        )
        flash(f'World "{worldname}" will be created on server start. Old world backed up.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')

    return redirect(url_for('world'))


# ============================================================
# Routes — Config
# ============================================================

@app.route('/config')
@login_required
def config():
    server_config = {}
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    server_config[key.strip()] = value.strip()

    tshock_config = {}
    if Path(TSHOCK_CONFIG).exists():
        with open(TSHOCK_CONFIG) as f:
            try:
                data = json.load(f)
                tshock_config = data.get('Settings', {})
            except Exception:
                pass

    version_info = get_version_info()
    server_type = get_server_type()
    return render_template(
        'config.html',
        server_config=server_config,
        tshock_config=tshock_config,
        version=version_info,
        server_type=server_type,
    )


@app.route('/config/save', methods=['POST'])
@login_required
def save_config():
    config_keys = ['worldname', 'maxplayers', 'port', 'password', 'difficulty', 'autocreate', 'motd']

    lines = ['# Terraria Server Configuration', f'# Modified: {datetime.now().isoformat()}', '']
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


# ============================================================
# Routes — Mods (tModLoader only)
# ============================================================

# ------------------------------------------------------------------
# .tmod binary parser helpers
# ------------------------------------------------------------------

def _read_7bit_string(data, pos):
    """Read a .NET BinaryWriter 7-bit-encoded string from *data* at *pos*.

    Returns (decoded_string, next_pos).
    """
    length = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        length |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    text = data[pos:pos + length].decode('utf-8', errors='replace')
    return text, pos + length


def _read_dotnet_string_list(data, pos):
    """Read a .NET BinaryWriter list of strings terminated by an empty string.

    Returns (list_of_strings, next_pos).
    """
    items = []
    while True:
        s, pos = _read_7bit_string(data, pos)
        if not s:
            break
        items.append(s)
    return items, pos


def _parse_info_binary(data):
    """Parse tModLoader's binary Info file and return (mod_refs, weak_refs).

    Format (from BuildProperties.cs ToBytes/ReadFromStream):
      Sequence of tag strings (7-bit) followed by value(s), terminated by "".
      Tags with list values  : "modReferences", "weakReferences", "sortAfter",
                               "sortBefore", "dllReferences"  → ReadList()
      Tags with string value : "author", "version", "displayName", "homepage",
                               "description", "eacPath", "buildVersion", "modSource"
      Tags with byte value   : "side"
      Boolean flag tags      : "noCompile", "!playableOnPreview", "translationMod",
                               "!hideCode", "!hideResources", "includeSource"
                               (no value follows — tag alone signals true)

    ModReference strings are "ModName" or "ModName@version".
    """
    STRING_VALUE_TAGS = frozenset({
        'author', 'version', 'displayName', 'homepage',
        'description', 'eacPath', 'buildVersion', 'modSource',
    })
    LIST_VALUE_TAGS = frozenset({
        'modReferences', 'weakReferences',
        'sortAfter', 'sortBefore', 'dllReferences',
    })

    pos = 0
    mod_refs = []
    weak_refs = []

    while pos < len(data):
        tag, pos = _read_7bit_string(data, pos)
        if not tag:
            break

        if tag == 'modReferences':
            refs, pos = _read_dotnet_string_list(data, pos)
            mod_refs = [r.split('@')[0] for r in refs]
        elif tag == 'weakReferences':
            refs, pos = _read_dotnet_string_list(data, pos)
            weak_refs = [r.split('@')[0] for r in refs]
        elif tag in LIST_VALUE_TAGS:
            _, pos = _read_dotnet_string_list(data, pos)
        elif tag in STRING_VALUE_TAGS:
            _, pos = _read_7bit_string(data, pos)
        elif tag == 'side':
            pos += 1  # single byte enum
        # boolean flag tags have no payload — the tag itself is the value

    return mod_refs, weak_refs


def _read_tmod_file_entry(raw, pos, file_data_start):
    """Given the (name, offset, u_len, c_len) table, extract and optionally
    decompress the file bytes.  Returns raw bytes."""
    name_pos, offset, uncompressed_len, compressed_len = pos
    start = file_data_start + offset
    file_bytes = raw[start:start + compressed_len]
    if uncompressed_len != compressed_len:
        file_bytes = zlib.decompress(file_bytes, wbits=-15)
    return file_bytes


def _parse_tmod_file_table(raw, pos):
    """Parse mod name/version and file table from signed data section.

    Returns (mod_name, entries, file_data_start) where entries is a list of
    (name, offset_from_data_start, uncompressed_len, compressed_len).
    """
    mod_name, pos = _read_7bit_string(raw, pos)
    _, pos = _read_7bit_string(raw, pos)   # mod version

    file_count = int.from_bytes(raw[pos:pos + 4], 'little')
    pos += 4

    entries = []
    running_offset = 0
    for _ in range(file_count):
        name, pos = _read_7bit_string(raw, pos)
        u_len = int.from_bytes(raw[pos:pos + 4], 'little'); pos += 4
        c_len = int.from_bytes(raw[pos:pos + 4], 'little'); pos += 4
        entries.append((name, running_offset, u_len, c_len))
        running_offset += c_len

    file_data_start = pos
    return mod_name, entries, file_data_start


def _parse_tmod_dependencies(tmod_path):
    """Return list of hard-required mod names from the Info file inside a .tmod.

    File format header (TmodFile.cs):
      "TMOD"   4 bytes
      version  7-bit string
      hash     20 bytes
      sig      256 bytes
      datalen  int32  ← skipped, signed data follows immediately (not compressed)

    Dependencies come from the binary Info file (BuildProperties.cs):
      modReferences  = hard deps  (returned)
      weakReferences = optional   (ignored — mod works without them)
    """
    try:
        with open(tmod_path, 'rb') as fh:
            raw = fh.read()

        if raw[:4] != b'TMOD':
            return []

        pos = 4
        _, pos = _read_7bit_string(raw, pos)  # tML version
        pos += 20 + 256 + 4                   # hash + sig + datalen

        _, entries, file_data_start = _parse_tmod_file_table(raw, pos)

        for name, offset, u_len, c_len in entries:
            if name == 'Info':
                start = file_data_start + offset
                file_bytes = raw[start:start + c_len]
                if u_len != c_len:
                    file_bytes = zlib.decompress(file_bytes, wbits=-15)
                mod_refs, _ = _parse_info_binary(file_bytes)
                return mod_refs

        # Fallback: old mods may still ship build.txt
        for name, offset, u_len, c_len in entries:
            if name == 'build.txt':
                start = file_data_start + offset
                file_bytes = raw[start:start + c_len]
                if u_len != c_len:
                    file_bytes = zlib.decompress(file_bytes, wbits=-15)
                for line in file_bytes.decode('utf-8', errors='replace').splitlines():
                    line = line.strip()
                    if line.startswith('modReferences') and '=' in line:
                        return [d.strip() for d in line.split('=', 1)[1].split(',') if d.strip()]
                return []

    except Exception:
        pass
    return []


def _debug_tmod(tmod_path):
    """Return diagnostic info about a .tmod file (for /api/mods/debug)."""
    result = {'path': tmod_path, 'exists': os.path.exists(tmod_path)}
    if not result['exists']:
        return result
    try:
        with open(tmod_path, 'rb') as fh:
            raw = fh.read()

        result['size'] = len(raw)
        result['magic_ok'] = raw[:4] == b'TMOD'
        if not result['magic_ok']:
            return result

        pos = 4
        tml_ver, pos = _read_7bit_string(raw, pos)
        result['tml_version'] = tml_ver
        pos += 20 + 256
        result['datalen'] = int.from_bytes(raw[pos:pos + 4], 'little')
        pos += 4
        result['signed_data_start'] = pos

        mod_name, entries, file_data_start = _parse_tmod_file_table(raw, pos)
        result['mod_name'] = mod_name
        result['file_count'] = len(entries)
        result['files'] = [
            {'name': n, 'uncompressed': u, 'compressed': c}
            for n, _, u, c in entries
        ]

        # Parse Info or build.txt
        for name, offset, u_len, c_len in entries:
            if name == 'Info':
                start = file_data_start + offset
                file_bytes = raw[start:start + c_len]
                if u_len != c_len:
                    file_bytes = zlib.decompress(file_bytes, wbits=-15)
                mod_refs, weak_refs = _parse_info_binary(file_bytes)
                result['mod_references'] = mod_refs
                result['weak_references'] = weak_refs
                result['dependencies'] = mod_refs
                result['parse_ok'] = True
                return result

        result['parse_ok'] = False
        result['parse_error'] = 'Info file not found in .tmod'

    except Exception as exc:
        result['exception'] = str(exc)
    return result


# ------------------------------------------------------------------
# steamcmd download helper
# ------------------------------------------------------------------

def _download_mod_from_workshop(steamcmd, workshop_id):
    """Download a Workshop item and copy the .tmod into MODS_DIR.

    Returns (mod_name, None) on success or (None, error_message) on failure.
    Does NOT modify enabled.json.
    """
    try:
        result = subprocess.run(
            [steamcmd,
             '+login', 'anonymous',
             '+workshop_download_item', TERRARIA_APP_ID, workshop_id,
             '+quit'],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, 'HOME': TERRARIA_DIR}
        )

        workshop_dir = os.path.join(
            TERRARIA_DIR, 'Steam', 'steamapps', 'workshop',
            'content', TERRARIA_APP_ID, workshop_id
        )

        if not os.path.isdir(workshop_dir):
            tail = (result.stdout + result.stderr)[-600:]
            return None, f'Workshop item {workshop_id} download failed. steamcmd: {tail}'

        tmod_files = [
            os.path.join(root, f)
            for root, _, files in os.walk(workshop_dir)
            for f in files if f.endswith('.tmod')
        ]

        if not tmod_files:
            return None, f'No .tmod file found in Workshop item {workshop_id}'

        tmod_file = max(tmod_files, key=os.path.getmtime)
        os.makedirs(MODS_DIR, exist_ok=True)
        dest = os.path.join(MODS_DIR, os.path.basename(tmod_file))
        shutil.copy2(tmod_file, dest)
        mod_name = os.path.basename(tmod_file)[:-5]
        return mod_name, None

    except subprocess.TimeoutExpired:
        return None, f'Download of Workshop item {workshop_id} timed out (5 min)'
    except Exception as exc:
        return None, f'Error downloading Workshop item {workshop_id}: {exc}'


# ------------------------------------------------------------------
# Dependency auto-installer
# ------------------------------------------------------------------

def _ensure_mod_dependencies(tmod_path, steamcmd):
    """Parse *tmod_path* for modReferences and auto-install any that are missing.

    Returns a list of (ok: bool, message: str) tuples to be flashed to the user.
    """
    messages = []
    deps = _parse_tmod_dependencies(tmod_path)
    if not deps:
        return messages

    for dep in deps:
        dep_file = os.path.join(MODS_DIR, f'{dep}.tmod')

        if os.path.exists(dep_file):
            # Already present — just make sure it's enabled
            enabled = _get_enabled_mods()
            if not enabled.get(dep, False):
                enabled[dep] = True
                _save_enabled_mods(enabled)
                messages.append((True, f'Dependency "{dep}" already installed — enabled it.'))
            continue

        workshop_id = KNOWN_WORKSHOP_IDS.get(dep)
        if not workshop_id:
            messages.append((
                False,
                f'Dependency "{dep}" is required but its Workshop ID is unknown. '
                f'Install it manually and re-enable the mod.'
            ))
            continue

        mod_name, err = _download_mod_from_workshop(steamcmd, workshop_id)
        if err:
            messages.append((False, f'Failed to auto-install dependency "{dep}": {err}'))
        else:
            enabled = _get_enabled_mods()
            enabled[mod_name] = True
            _save_enabled_mods(enabled)
            messages.append((True, f'Auto-installed dependency "{dep}" (Workshop {workshop_id}).'))

    return messages


def _get_enabled_mods():
    """Return dict {ModName: bool} regardless of enabled.json format.

    tModLoader stores enabled.json as a list of enabled mod names.
    We normalise to a dict so the rest of the code is uniform.
    """
    enabled_file = os.path.join(MODS_DIR, 'enabled.json')
    if os.path.exists(enabled_file):
        try:
            with open(enabled_file) as f:
                data = json.load(f)
            if isinstance(data, list):
                return {name: True for name in data}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_enabled_mods(enabled):
    """Write enabled.json in tModLoader's native list format."""
    os.makedirs(MODS_DIR, exist_ok=True)
    enabled_file = os.path.join(MODS_DIR, 'enabled.json')
    # tModLoader expects a list of enabled mod names
    enabled_list = [name for name, active in enabled.items() if active]
    with open(enabled_file, 'w') as f:
        json.dump(enabled_list, f, indent=2)


def _list_mods():
    """Scan MODS_DIR for .tmod files and return metadata list."""
    mods = []
    if not os.path.isdir(MODS_DIR):
        return mods

    enabled = _get_enabled_mods()

    for fname in sorted(os.listdir(MODS_DIR)):
        if not fname.endswith('.tmod'):
            continue
        mod_name = fname[:-5]
        fpath = os.path.join(MODS_DIR, fname)
        size_bytes = os.path.getsize(fpath)
        size_mb = round(size_bytes / (1024 * 1024), 2)
        mods.append({
            'name': mod_name,
            'filename': fname,
            'enabled': enabled.get(mod_name, False),
            'size_mb': size_mb,
        })

    return mods


@app.route('/mods')
@login_required
def mods():
    mod_list = _list_mods()
    server_type = get_server_type()
    return render_template('mods.html', mods=mod_list, server_type=server_type, mods_dir=MODS_DIR)


@app.route('/mods/toggle', methods=['POST'])
@login_required
def mods_toggle():
    mod_name = request.form.get('mod_name', '').strip()
    if not mod_name:
        flash('Mod name is required', 'error')
        return redirect(url_for('mods'))

    enabled = _get_enabled_mods()
    current = enabled.get(mod_name, False)
    enabled[mod_name] = not current
    _save_enabled_mods(enabled)

    action = 'enabled' if enabled[mod_name] else 'disabled'
    flash(f'Mod "{mod_name}" {action}. Restart the server to apply changes.', 'success')
    return redirect(url_for('mods'))


@app.route('/mods/upload', methods=['POST'])
@login_required
def mods_upload():
    if 'mod_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('mods'))

    f = request.files['mod_file']
    if not f.filename:
        flash('No file selected', 'error')
        return redirect(url_for('mods'))

    filename = secure_filename(f.filename)
    if not filename.endswith('.tmod'):
        flash('Only .tmod files are allowed', 'error')
        return redirect(url_for('mods'))

    os.makedirs(MODS_DIR, exist_ok=True)
    dest = os.path.join(MODS_DIR, filename)
    f.save(dest)

    mod_name = filename[:-5]
    # Auto-enable the newly uploaded mod
    enabled = _get_enabled_mods()
    enabled[mod_name] = True
    _save_enabled_mods(enabled)
    flash(f'Mod "{mod_name}" uploaded and enabled.', 'success')

    # Auto-install any missing dependencies if steamcmd is available
    steamcmd = STEAMCMD_BIN if os.path.exists(STEAMCMD_BIN) else shutil.which('steamcmd')
    if steamcmd:
        for ok, msg in _ensure_mod_dependencies(dest, steamcmd):
            flash(msg, 'success' if ok else 'error')
    else:
        deps = _parse_tmod_dependencies(dest)
        if deps:
            flash(
                f'This mod requires: {", ".join(deps)}. '
                f'Install steamcmd (re-run install.sh --tmodloader) to auto-install dependencies.',
                'error'
            )

    flash('Restart the server to apply changes.', 'success')
    return redirect(url_for('mods'))


@app.route('/mods/delete', methods=['POST'])
@login_required
def mods_delete():
    mod_name = request.form.get('mod_name', '').strip()
    if not mod_name:
        flash('Mod name is required', 'error')
        return redirect(url_for('mods'))

    # Basic safety check: ensure we're deleting from MODS_DIR only
    filename = secure_filename(mod_name + '.tmod')
    target = os.path.join(MODS_DIR, filename)
    if not target.startswith(MODS_DIR):
        flash('Invalid mod path', 'error')
        return redirect(url_for('mods'))

    if os.path.exists(target):
        os.remove(target)
        # Remove from enabled.json too
        enabled = _get_enabled_mods()
        enabled.pop(mod_name, None)
        _save_enabled_mods(enabled)
        flash(f'Mod "{mod_name}" deleted. Restart the server to apply.', 'success')
    else:
        flash(f'Mod file not found: {filename}', 'error')

    return redirect(url_for('mods'))


@app.route('/mods/workshop', methods=['POST'])
@login_required
def mods_workshop():
    workshop_id = request.form.get('workshop_id', '').strip()

    if not workshop_id.isdigit():
        flash('Invalid Workshop ID — must be a number only', 'error')
        return redirect(url_for('mods'))

    steamcmd = STEAMCMD_BIN if os.path.exists(STEAMCMD_BIN) else shutil.which('steamcmd')
    if not steamcmd:
        flash('steamcmd not found. Re-run install.sh --tmodloader to install it.', 'error')
        return redirect(url_for('mods'))

    mod_name, err = _download_mod_from_workshop(steamcmd, workshop_id)
    if err:
        flash(err, 'error')
        return redirect(url_for('mods'))

    enabled = _get_enabled_mods()
    enabled[mod_name] = True
    _save_enabled_mods(enabled)
    flash(f'Mod "{mod_name}" installed and enabled!', 'success')

    # Auto-install any missing dependencies declared in the .tmod
    dest = os.path.join(MODS_DIR, f'{mod_name}.tmod')
    for ok, msg in _ensure_mod_dependencies(dest, steamcmd):
        flash(msg, 'success' if ok else 'error')

    flash('Restart the server to apply changes.', 'success')
    return redirect(url_for('mods'))


@app.route('/mods/search')
@login_required
def mods_search():
    return render_template('mods_search.html')


# ============================================================
# Routes — Update / version info
# ============================================================

def get_version_info():
    server_type = get_server_type()
    current = _stored_version()
    latest = 'unknown'

    try:
        if server_type == 'tshock':
            resp = requests.get(
                'https://api.github.com/repos/Pryaxis/TShock/releases/latest', timeout=5
            )
            if resp.ok:
                latest = resp.json().get('tag_name', 'unknown')
        elif server_type == 'tmodloader':
            resp = requests.get(
                'https://api.github.com/repos/tModLoader/tModLoader/releases/latest', timeout=5
            )
            if resp.ok:
                latest = resp.json().get('tag_name', 'unknown')
        else:
            resp = requests.get(
                'https://terraria.org/api/get/dedicated-servers-names', timeout=5
            )
            if resp.ok:
                files = resp.json()
                if files:
                    import re
                    match = re.search(r'(\d+)', files[0])
                    if match:
                        ver = match.group(1)
                        latest = f"1.4.5.{ver[-1]}" if len(ver) == 4 else ver
    except Exception:
        pass

    return {
        'current': current,
        'latest': latest,
        'server_type': server_type,
        'update_available': current != latest and latest != 'unknown',
    }


@app.route('/update', methods=['POST'])
@login_required
def update_server():
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


# ============================================================
# API endpoints (for JS polling)
# ============================================================

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


@app.route('/api/mods')
@login_required
def api_mods():
    return jsonify(_list_mods())


@app.route('/api/mods/debug')
@login_required
def api_mods_debug():
    """Diagnostic endpoint: parse every .tmod and report dependencies + format info."""
    results = []
    if os.path.isdir(MODS_DIR):
        for fname in sorted(os.listdir(MODS_DIR)):
            if fname.endswith('.tmod'):
                results.append(_debug_tmod(os.path.join(MODS_DIR, fname)))
    return jsonify(results)


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    print("=" * 50)
    print("Terraria Web Admin Panel")
    print("=" * 50)
    print(f"Server directory: {TERRARIA_DIR}")
    print(f"Server type:      {get_server_type()}")
    print(f"Mods directory:   {MODS_DIR}")
    print(f"Access:           http://0.0.0.0:5000")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5000, debug=False)
