from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from ..decorators import login_required, require_role, ROLE_LEVELS
from ..services.auth import get_admins, save_admins

bp = Blueprint('admins', __name__)


@bp.route('/admins')
@require_role('superadmin')
def admins_page():
    cfg = current_app.terraria_config
    admins_data = get_admins(cfg)
    admin_list = [
        {
            'username': u,
            'role': d.get('role', 'admin'),
            'created_at': d.get('created_at', ''),
        }
        for u, d in admins_data.items()
    ]
    return render_template(
        'admins.html',
        admins=admin_list,
        roles=list(ROLE_LEVELS.keys()),
        current_user=session.get('username'),
    )


@bp.route('/admins/add', methods=['POST'])
@require_role('superadmin')
def admins_add():
    cfg = current_app.terraria_config
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'admin')
    if not username or not password:
        flash('Username and password are required', 'error')
        return redirect(url_for('admins.admins_page'))
    if role not in ROLE_LEVELS:
        flash('Invalid role', 'error')
        return redirect(url_for('admins.admins_page'))
    admins_data = get_admins(cfg)
    if username in admins_data:
        flash(f'User "{username}" already exists', 'error')
        return redirect(url_for('admins.admins_page'))
    admins_data[username] = {
        'password_hash': generate_password_hash(password),
        'role': role,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    save_admins(admins_data, cfg)
    flash(f'Admin "{username}" created with role "{role}".', 'success')
    return redirect(url_for('admins.admins_page'))


@bp.route('/admins/delete', methods=['POST'])
@require_role('superadmin')
def admins_delete():
    cfg = current_app.terraria_config
    username = request.form.get('username', '').strip()
    if username == session.get('username'):
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('admins.admins_page'))
    admins_data = get_admins(cfg)
    superadmins = [u for u, d in admins_data.items() if d.get('role') == 'superadmin']
    if username in superadmins and len(superadmins) <= 1:
        flash('Cannot delete the last superadmin', 'error')
        return redirect(url_for('admins.admins_page'))
    if username in admins_data:
        del admins_data[username]
        save_admins(admins_data, cfg)
        flash(f'Admin "{username}" deleted.', 'success')
    else:
        flash(f'User "{username}" not found', 'error')
    return redirect(url_for('admins.admins_page'))


@bp.route('/admins/role', methods=['POST'])
@require_role('superadmin')
def admins_role():
    cfg = current_app.terraria_config
    username = request.form.get('username', '').strip()
    new_role = request.form.get('role', '').strip()
    if new_role not in ROLE_LEVELS:
        flash('Invalid role', 'error')
        return redirect(url_for('admins.admins_page'))
    admins_data = get_admins(cfg)
    if username not in admins_data:
        flash(f'User "{username}" not found', 'error')
        return redirect(url_for('admins.admins_page'))
    if admins_data[username].get('role') == 'superadmin' and new_role != 'superadmin':
        superadmins = [u for u, d in admins_data.items() if d.get('role') == 'superadmin']
        if len(superadmins) <= 1:
            flash('Cannot demote the last superadmin', 'error')
            return redirect(url_for('admins.admins_page'))
    admins_data[username]['role'] = new_role
    save_admins(admins_data, cfg)
    flash(f'Role for "{username}" changed to "{new_role}".', 'success')
    return redirect(url_for('admins.admins_page'))


@bp.route('/admins/password', methods=['POST'])
@login_required
def admins_password():
    cfg = current_app.terraria_config
    target = request.form.get('username', '').strip()
    new_password = request.form.get('password', '').strip()
    current_user = session.get('username')
    current_role = session.get('role', 'viewer')
    if not new_password or len(new_password) < 6:
        flash('Password must be at least 6 characters', 'error')
        return redirect(url_for('admins.admins_page'))
    if target != current_user and ROLE_LEVELS.get(current_role, 0) < ROLE_LEVELS['superadmin']:
        flash("Insufficient permissions to change another user's password", 'error')
        return redirect(url_for('admins.admins_page'))
    admins_data = get_admins(cfg)
    if target not in admins_data:
        flash(f'User "{target}" not found', 'error')
        return redirect(url_for('admins.admins_page'))
    admins_data[target]['password_hash'] = generate_password_hash(new_password)
    save_admins(admins_data, cfg)
    flash(f'Password for "{target}" updated.', 'success')
    return redirect(url_for('admins.admins_page'))
