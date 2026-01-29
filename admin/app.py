#!/usr/bin/env python3
"""
Terraria Server Admin Panel
Web interface for managing Terraria dedicated server configuration
"""

import os
import subprocess
import re
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'terraria-admin-secret-change-me')

# Configuration
SERVER_DIR = os.environ.get('TERRARIA_DIR', '/opt/terraria')
CONFIG_FILE = os.path.join(SERVER_DIR, 'serverconfig.txt')
SERVICE_NAME = 'terraria'

# Server config options with descriptions
CONFIG_OPTIONS = {
    'world': {'type': 'text', 'label': 'World File Path', 'description': 'Full path to the world file'},
    'autocreate': {'type': 'select', 'label': 'Auto Create World', 'options': [
        ('0', 'None'),
        ('1', 'Small'),
        ('2', 'Medium'),
        ('3', 'Large')
    ], 'description': 'Automatically create world if not exists'},
    'worldname': {'type': 'text', 'label': 'World Name', 'description': 'Name for auto-created world'},
    'difficulty': {'type': 'select', 'label': 'Difficulty', 'options': [
        ('0', 'Classic'),
        ('1', 'Expert'),
        ('2', 'Master'),
        ('3', 'Journey')
    ], 'description': 'World difficulty mode'},
    'maxplayers': {'type': 'number', 'label': 'Max Players', 'min': 1, 'max': 255, 'description': 'Maximum number of players'},
    'port': {'type': 'number', 'label': 'Port', 'min': 1, 'max': 65535, 'description': 'Server port (default: 7777)'},
    'password': {'type': 'password', 'label': 'Password', 'description': 'Server password (empty = no password)'},
    'motd': {'type': 'text', 'label': 'MOTD', 'description': 'Message of the day'},
    'worldpath': {'type': 'text', 'label': 'Worlds Directory', 'description': 'Directory for world files'},
    'secure': {'type': 'select', 'label': 'Anti-Cheat', 'options': [
        ('0', 'Disabled'),
        ('1', 'Enabled')
    ], 'description': 'Enable anti-cheat protection'},
    'language': {'type': 'select', 'label': 'Language', 'options': [
        ('en-US', 'English'),
        ('de-DE', 'German'),
        ('it-IT', 'Italian'),
        ('fr-FR', 'French'),
        ('es-ES', 'Spanish'),
        ('ru-RU', 'Russian'),
        ('zh-Hans', 'Chinese Simplified'),
        ('pt-BR', 'Portuguese'),
        ('pl-PL', 'Polish')
    ], 'description': 'Server language'},
    'upnp': {'type': 'select', 'label': 'UPnP', 'options': [
        ('0', 'Disabled'),
        ('1', 'Enabled')
    ], 'description': 'Automatic port forwarding'},
    'npcstream': {'type': 'number', 'label': 'NPC Stream', 'min': 0, 'max': 200, 'description': 'NPC streaming range (0 = off)'},
    'priority': {'type': 'select', 'label': 'Process Priority', 'options': [
        ('0', 'Realtime'),
        ('1', 'High'),
        ('2', 'Above Normal'),
        ('3', 'Normal'),
        ('4', 'Below Normal'),
        ('5', 'Idle')
    ], 'description': 'Server process priority'},
}


def read_config() -> dict:
    """Read server configuration file"""
    config = {}
    if not Path(CONFIG_FILE).exists():
        return config

    with open(CONFIG_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    return config


def write_config(config: dict):
    """Write server configuration file"""
    lines = ['# Terraria Server Configuration', '# Managed by Terraria Admin Panel', '']

    for key, value in sorted(config.items()):
        lines.append(f'{key}={value}')

    with open(CONFIG_FILE, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def get_server_status() -> dict:
    """Get server status via systemctl"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        is_running = result.stdout.strip() == 'active'

        status_result = subprocess.run(
            ['systemctl', 'status', SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )

        return {
            'running': is_running,
            'status': 'Running' if is_running else 'Stopped',
            'details': status_result.stdout
        }
    except Exception as e:
        return {'running': False, 'status': 'Unknown', 'details': str(e)}


def control_server(action: str) -> tuple[bool, str]:
    """Start/stop/restart server"""
    if action not in ('start', 'stop', 'restart'):
        return False, 'Invalid action'

    try:
        result = subprocess.run(
            ['sudo', 'systemctl', action, SERVICE_NAME],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, f'Server {action}ed successfully'
        return False, result.stderr or 'Command failed'
    except Exception as e:
        return False, str(e)


def get_worlds() -> list:
    """List available world files"""
    worlds = []
    worlds_dir = Path(SERVER_DIR) / 'worlds'
    if worlds_dir.exists():
        for f in worlds_dir.glob('*.wld'):
            worlds.append({
                'name': f.stem,
                'path': str(f),
                'size': f.stat().st_size // 1024  # KB
            })
    return worlds


@app.route('/')
def index():
    config = read_config()
    status = get_server_status()
    worlds = get_worlds()
    return render_template('index.html',
                         config=config,
                         options=CONFIG_OPTIONS,
                         status=status,
                         worlds=worlds)


@app.route('/save', methods=['POST'])
def save_config():
    config = {}
    for key in CONFIG_OPTIONS:
        value = request.form.get(key, '')
        if value or key == 'password':  # Allow empty password
            config[key] = value

    try:
        write_config(config)
        flash('Configuration saved successfully!', 'success')
    except Exception as e:
        flash(f'Error saving configuration: {e}', 'error')

    return redirect(url_for('index'))


@app.route('/server/<action>', methods=['POST'])
def server_control(action):
    success, message = control_server(action)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('index'))


@app.route('/api/status')
def api_status():
    return jsonify(get_server_status())


if __name__ == '__main__':
    # Create templates directory
    templates_dir = Path(__file__).parent / 'templates'
    templates_dir.mkdir(exist_ok=True)

    print(f"Terraria Admin Panel")
    print(f"Config: {CONFIG_FILE}")
    print(f"Access: http://localhost:5000")

    app.run(host='0.0.0.0', port=5000, debug=True)
