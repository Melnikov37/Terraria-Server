import os
import shutil

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from ..decorators import login_required
from ..services.server import get_server_type
from ..services.mods import (
    list_mods, get_enabled_mods, save_enabled_mods,
    get_mod_meta, record_mod_installed, remove_mod_meta,
    download_mod_from_workshop, ensure_mod_dependencies, parse_tmod_dependencies,
)
from ..services.discord import discord_notify

bp = Blueprint('mods', __name__)


@bp.route('/mods')
@login_required
def mods():
    cfg = current_app.terraria_config
    mod_list = list_mods(cfg)
    server_type = get_server_type(cfg)
    return render_template('mods.html', mods=mod_list, server_type=server_type, mods_dir=cfg.MODS_DIR)


@bp.route('/mods/toggle', methods=['POST'])
@login_required
def mods_toggle():
    cfg = current_app.terraria_config
    mod_name = request.form.get('mod_name', '').strip()
    if not mod_name:
        flash('Mod name is required', 'error')
        return redirect(url_for('mods.mods'))

    enabled = get_enabled_mods(cfg)
    current = enabled.get(mod_name, False)
    enabled[mod_name] = not current
    save_enabled_mods(enabled, cfg)

    action = 'enabled' if enabled[mod_name] else 'disabled'
    flash(f'Mod "{mod_name}" {action}. Restart the server to apply changes.', 'success')
    return redirect(url_for('mods.mods'))


@bp.route('/mods/upload', methods=['POST'])
@login_required
def mods_upload():
    cfg = current_app.terraria_config
    if 'mod_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('mods.mods'))

    f = request.files['mod_file']
    if not f.filename:
        flash('No file selected', 'error')
        return redirect(url_for('mods.mods'))

    filename = secure_filename(f.filename)
    if not filename.endswith('.tmod'):
        flash('Only .tmod files are allowed', 'error')
        return redirect(url_for('mods.mods'))

    os.makedirs(cfg.MODS_DIR, exist_ok=True)
    dest = os.path.join(cfg.MODS_DIR, filename)
    f.save(dest)

    mod_name = filename[:-5]
    enabled = get_enabled_mods(cfg)
    enabled[mod_name] = True
    save_enabled_mods(enabled, cfg)
    record_mod_installed(mod_name, dest, cfg)
    flash(f'Mod "{mod_name}" uploaded and enabled.', 'success')

    steamcmd = cfg.STEAMCMD_BIN if os.path.exists(cfg.STEAMCMD_BIN) else shutil.which('steamcmd')
    if steamcmd:
        for ok, msg in ensure_mod_dependencies(dest, steamcmd, cfg):
            flash(msg, 'success' if ok else 'error')
    else:
        deps = parse_tmod_dependencies(dest)
        if deps:
            flash(
                f'This mod requires: {", ".join(deps)}. '
                f'Install steamcmd (re-run install.sh --tmodloader) to auto-install dependencies.',
                'error'
            )

    flash('Restart the server to apply changes.', 'success')
    return redirect(url_for('mods.mods'))


@bp.route('/mods/delete', methods=['POST'])
@login_required
def mods_delete():
    cfg = current_app.terraria_config
    mod_name = request.form.get('mod_name', '').strip()
    if not mod_name:
        flash('Mod name is required', 'error')
        return redirect(url_for('mods.mods'))

    filename = secure_filename(mod_name + '.tmod')
    target = os.path.join(cfg.MODS_DIR, filename)
    if not target.startswith(cfg.MODS_DIR.rstrip(os.sep) + os.sep):
        flash('Invalid mod path', 'error')
        return redirect(url_for('mods.mods'))

    if os.path.exists(target):
        os.remove(target)
        enabled = get_enabled_mods(cfg)
        enabled.pop(mod_name, None)
        save_enabled_mods(enabled, cfg)
        remove_mod_meta(mod_name, cfg)
        flash(f'Mod "{mod_name}" deleted. Restart the server to apply.', 'success')
    else:
        flash(f'Mod file not found: {filename}', 'error')

    return redirect(url_for('mods.mods'))


@bp.route('/mods/workshop', methods=['POST'])
@login_required
def mods_workshop():
    cfg = current_app.terraria_config
    workshop_id = request.form.get('workshop_id', '').strip()

    if not workshop_id.isdigit():
        flash('Invalid Workshop ID — must be a number only', 'error')
        return redirect(url_for('mods.mods'))

    steamcmd = cfg.STEAMCMD_BIN if os.path.exists(cfg.STEAMCMD_BIN) else shutil.which('steamcmd')
    if not steamcmd:
        flash('steamcmd not found. Re-run install.sh --tmodloader to install it.', 'error')
        return redirect(url_for('mods.mods'))

    mod_name, err = download_mod_from_workshop(steamcmd, workshop_id, cfg)
    if err:
        flash(err, 'error')
        return redirect(url_for('mods.mods'))

    dest = os.path.join(cfg.MODS_DIR, f'{mod_name}.tmod')
    enabled = get_enabled_mods(cfg)
    enabled[mod_name] = True
    save_enabled_mods(enabled, cfg)
    record_mod_installed(mod_name, dest, cfg, workshop_id)
    flash(f'Mod "{mod_name}" installed and enabled!', 'success')
    discord_notify(
        f'Mod installed: **{mod_name}** (Workshop {workshop_id})',
        cfg, color=0x58a6ff, event='mod_install'
    )

    for ok, msg in ensure_mod_dependencies(dest, steamcmd, cfg):
        flash(msg, 'success' if ok else 'error')

    flash('Restart the server to apply changes.', 'success')
    return redirect(url_for('mods.mods'))


@bp.route('/mods/update', methods=['POST'])
@login_required
def mods_update_one():
    cfg = current_app.terraria_config
    mod_name = request.form.get('mod_name', '').strip()
    if not mod_name:
        flash('Mod name is required', 'error')
        return redirect(url_for('mods.mods'))

    meta = get_mod_meta(cfg)
    workshop_id = meta.get(mod_name, {}).get('workshop_id') or cfg.KNOWN_WORKSHOP_IDS.get(mod_name)
    if not workshop_id:
        flash(f'No Workshop ID known for "{mod_name}". Cannot auto-update.', 'error')
        return redirect(url_for('mods.mods'))

    steamcmd = cfg.STEAMCMD_BIN if os.path.exists(cfg.STEAMCMD_BIN) else shutil.which('steamcmd')
    if not steamcmd:
        flash('steamcmd not found', 'error')
        return redirect(url_for('mods.mods'))

    old_version = meta.get(mod_name, {}).get('version', '?')
    new_mod_name, err = download_mod_from_workshop(steamcmd, workshop_id, cfg)
    if err:
        flash(err, 'error')
        return redirect(url_for('mods.mods'))

    dest = os.path.join(cfg.MODS_DIR, f'{new_mod_name}.tmod')
    record_mod_installed(new_mod_name, dest, cfg, workshop_id)
    new_version = get_mod_meta(cfg).get(new_mod_name, {}).get('version', '?')

    if old_version != new_version:
        flash(f'"{mod_name}" updated: {old_version} → {new_version}. Restart server to apply.', 'success')
    else:
        flash(f'"{mod_name}" is already up to date (v{new_version}).', 'success')

    return redirect(url_for('mods.mods'))


@bp.route('/mods/update_all', methods=['POST'])
@login_required
def mods_update_all():
    cfg = current_app.terraria_config
    steamcmd = cfg.STEAMCMD_BIN if os.path.exists(cfg.STEAMCMD_BIN) else shutil.which('steamcmd')
    if not steamcmd:
        flash('steamcmd not found', 'error')
        return redirect(url_for('mods.mods'))

    meta = get_mod_meta(cfg)
    updated = []
    skipped = []
    failed = []

    for mod in list_mods(cfg):
        mod_name = mod['name']
        workshop_id = mod.get('workshop_id')
        if not workshop_id:
            skipped.append(mod_name)
            continue

        old_version = meta.get(mod_name, {}).get('version', '?')
        new_mod_name, err = download_mod_from_workshop(steamcmd, workshop_id, cfg)
        if err:
            failed.append(f'{mod_name}: {err}')
            continue

        dest = os.path.join(cfg.MODS_DIR, f'{new_mod_name}.tmod')
        record_mod_installed(new_mod_name, dest, cfg, workshop_id)
        new_version = get_mod_meta(cfg).get(new_mod_name, {}).get('version', '?')
        if old_version != new_version:
            updated.append(f'{mod_name}: {old_version} → {new_version}')

    if updated:
        flash(f'Updated {len(updated)} mods — restart to apply: {", ".join(updated)}', 'success')
    else:
        flash('All mods are up to date.', 'success')
    if skipped:
        flash(f'Skipped (no Workshop ID): {", ".join(skipped)}', 'success')
    for msg in failed:
        flash(f'Failed: {msg}', 'error')

    return redirect(url_for('mods.mods'))


@bp.route('/mods/search')
@login_required
def mods_search():
    return render_template('mods_search.html')


@bp.route('/mods/public')
def mods_public():
    cfg = current_app.terraria_config
    enabled_mods = [m for m in list_mods(cfg) if m['enabled']]
    server_type = get_server_type(cfg)
    return render_template('mods_public.html', mods=enabled_mods, server_type=server_type)
