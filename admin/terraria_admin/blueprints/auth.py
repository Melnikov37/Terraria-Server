import secrets

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        token = request.form.get('token', '')
        expected = current_app.terraria_config.ADMIN_TOKEN
        if expected and secrets.compare_digest(token, expected):
            session['logged_in'] = True
            return redirect(url_for('dashboard.dashboard'))
        flash('Invalid token', 'error')
    return render_template('login.html')


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
