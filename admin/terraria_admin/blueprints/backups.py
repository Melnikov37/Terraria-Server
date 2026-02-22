import os
import shutil
import subprocess
import time

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..decorators import login_required
from ..services.backups import create_backup, list_backups, prune_auto_backups
from ..services.discord import discord_notify

bp = Blueprint('backups', __name__)


@bp.route('/backups')
@login_required
def backups():
    cfg = current_app.terraria_config
    return render_template(
        'backups.html',
        backups=list_backups(cfg),
        auto_interval=cfg.AUTO_BACKUP_INTERVAL_HOURS,
        keep_count=cfg.BACKUP_KEEP_COUNT,
    )


@bp.route('/backups/create', methods=['POST'])
@login_required
def backups_create():
    cfg = current_app.terraria_config
    name, err = create_backup(cfg, 'manual')
    if err:
        flash(f'Backup failed: {err}', 'error')
    else:
        flash(f'Backup created: {name}', 'success')
        discord_notify(f'World backup created: `{name}`', cfg, color=0x58a6ff, event='backup')
    return redirect(url_for('backups.backups'))


@bp.route('/backups/restore', methods=['POST'])
@login_required
def backups_restore():
    cfg = current_app.terraria_config
    backup_name = request.form.get('backup_name', '').strip()
    if not backup_name or os.sep in backup_name or '..' in backup_name:
        flash('Invalid backup name', 'error')
        return redirect(url_for('backups.backups'))
    backup_path = os.path.join(cfg.BACKUPS_DIR, backup_name)
    if not os.path.isdir(backup_path):
        flash('Backup not found', 'error')
        return redirect(url_for('backups.backups'))
    try:
        subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', 'stop', 'terraria.service'],
            capture_output=True, timeout=30
        )
        time.sleep(3)
        os.makedirs(cfg.WORLDS_DIR, exist_ok=True)
        for fname in os.listdir(backup_path):
            if fname.endswith('.wld'):
                shutil.copy2(
                    os.path.join(backup_path, fname),
                    os.path.join(cfg.WORLDS_DIR, fname)
                )
        subprocess.run(
            ['/usr/bin/sudo', '/usr/bin/systemctl', 'start', 'terraria.service'],
            capture_output=True, timeout=30
        )
        flash(f'Restored from "{backup_name}". Server restarting.', 'success')
    except Exception as exc:
        flash(f'Restore failed: {exc}', 'error')
    return redirect(url_for('backups.backups'))


@bp.route('/backups/delete', methods=['POST'])
@login_required
def backups_delete():
    cfg = current_app.terraria_config
    backup_name = request.form.get('backup_name', '').strip()
    if not backup_name or os.sep in backup_name or '..' in backup_name:
        flash('Invalid backup name', 'error')
        return redirect(url_for('backups.backups'))
    backup_path = os.path.join(cfg.BACKUPS_DIR, backup_name)
    if os.path.isdir(backup_path):
        shutil.rmtree(backup_path)
        flash(f'Backup "{backup_name}" deleted.', 'success')
    else:
        flash('Backup not found', 'error')
    return redirect(url_for('backups.backups'))
