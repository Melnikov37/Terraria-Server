import os
import shutil
import tempfile
import time

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for

from ..decorators import login_required
from ..services.backups import create_backup, list_backups, prune_auto_backups
from ..services.discord import discord_notify
from ..services.server import container_action

bp = Blueprint('backups', __name__)


def _safe_backup_path(backup_name, cfg):
    """Return resolved backup path only if it's within BACKUPS_DIR, else None."""
    if not backup_name or os.sep in backup_name or '..' in backup_name:
        return None
    candidate = os.path.join(cfg.BACKUPS_DIR, backup_name)
    real = os.path.realpath(candidate)
    real_base = os.path.realpath(cfg.BACKUPS_DIR)
    if not real.startswith(real_base + os.sep) and real != real_base:
        return None
    return candidate


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
    backup_path = _safe_backup_path(backup_name, cfg)
    if not backup_path:
        flash('Invalid backup name', 'error')
        return redirect(url_for('backups.backups'))
    if not os.path.isdir(backup_path):
        flash('Backup not found', 'error')
        return redirect(url_for('backups.backups'))
    try:
        try:
            container_action('stop', cfg)
        except Exception:
            pass
        time.sleep(3)
        os.makedirs(cfg.WORLDS_DIR, exist_ok=True)
        for fname in os.listdir(backup_path):
            if fname.endswith('.wld'):
                shutil.copy2(
                    os.path.join(backup_path, fname),
                    os.path.join(cfg.WORLDS_DIR, fname)
                )
        try:
            container_action('start', cfg)
        except Exception:
            pass
        flash(f'Restored from "{backup_name}". Server restarting.', 'success')
    except Exception as exc:
        flash(f'Restore failed: {exc}', 'error')
    return redirect(url_for('backups.backups'))


@bp.route('/backups/delete', methods=['POST'])
@login_required
def backups_delete():
    cfg = current_app.terraria_config
    backup_name = request.form.get('backup_name', '').strip()
    backup_path = _safe_backup_path(backup_name, cfg)
    if not backup_path:
        flash('Invalid backup name', 'error')
        return redirect(url_for('backups.backups'))
    if os.path.isdir(backup_path):
        shutil.rmtree(backup_path)
        flash(f'Backup "{backup_name}" deleted.', 'success')
    else:
        flash('Backup not found', 'error')
    return redirect(url_for('backups.backups'))


@bp.route('/backups/download/<backup_name>')
@login_required
def backups_download(backup_name):
    cfg = current_app.terraria_config
    backup_path = _safe_backup_path(backup_name, cfg)
    if not backup_path or not os.path.isdir(backup_path):
        flash('Backup not found', 'error')
        return redirect(url_for('backups.backups'))
    try:
        tmp_dir = tempfile.mkdtemp()
        zip_base = os.path.join(tmp_dir, backup_name)
        zip_path = shutil.make_archive(zip_base, 'zip', backup_path)
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f'{backup_name}.zip',
            mimetype='application/zip',
        )
    except Exception as exc:
        flash(f'Download failed: {exc}', 'error')
        return redirect(url_for('backups.backups'))
