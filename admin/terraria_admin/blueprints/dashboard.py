import os
import subprocess

from flask import Blueprint, current_app, flash, redirect, render_template, url_for

from ..decorators import login_required
from ..services.server import get_server_status, get_players
from ..services.discord import discord_notify

bp = Blueprint('dashboard', __name__)


@bp.route('/')
@login_required
def dashboard():
    cfg = current_app.terraria_config
    status = get_server_status(cfg)
    players = get_players(cfg) if status.get('online') else []
    return render_template('dashboard.html', status=status, players=players)


@bp.route('/server/<action>', methods=['POST'])
@login_required
def server_control(action):
    cfg = current_app.terraria_config
    if action not in ('start', 'stop', 'restart'):
        flash('Invalid action', 'error')
        return redirect(url_for('dashboard.dashboard'))

    try:
        result = subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', action, f'{cfg.SERVICE_NAME}.service'],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PATH': '/usr/bin:/bin'}
        )
        if result.returncode == 0:
            flash(f'Server {action}ed', 'success')
            if action == 'start':
                discord_notify('Server started :white_check_mark:', cfg, color=0x3fb950, event='start')
            elif action == 'stop':
                discord_notify('Server stopped :octagonal_sign:', cfg, color=0xf85149, event='stop')
            elif action == 'restart':
                discord_notify('Server restarted :arrows_counterclockwise:', cfg, color=0xd29922, event='stop')
        else:
            flash(f'Error: {result.stderr or result.stdout}', 'error')
    except Exception as e:
        flash(f'Error: {e}', 'error')

    return redirect(url_for('dashboard.dashboard'))
