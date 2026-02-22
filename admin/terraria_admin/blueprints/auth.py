from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ..services.auth import get_admins

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cfg = __import__('flask').current_app.terraria_config
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin = get_admins(cfg).get(username)
        if admin and check_password_hash(admin.get('password_hash', ''), password):
            session['logged_in'] = True
            session['username'] = username
            session['role'] = admin.get('role', 'admin')
            return redirect(url_for('dashboard.dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
