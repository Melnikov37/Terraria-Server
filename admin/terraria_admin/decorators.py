import functools

from flask import session, redirect, url_for, flash

ROLE_LEVELS = {'viewer': 0, 'admin': 1, 'superadmin': 2}


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def require_role(min_role='admin'):
    """Decorator: require login and a minimum role level."""
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('auth.login'))
            role = session.get('role', 'viewer')
            if ROLE_LEVELS.get(role, 0) < ROLE_LEVELS.get(min_role, 0):
                flash('Insufficient permissions', 'error')
                return redirect(url_for('dashboard.dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator
