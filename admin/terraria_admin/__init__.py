import os

from flask import Flask, jsonify, render_template, request, session

from .config import Config


def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder='../templates',
    )
    cfg = config_class()
    app.secret_key = cfg.SECRET_KEY
    app.config['SESSION_COOKIE_HTTPONLY'] = cfg.SESSION_COOKIE_HTTPONLY
    app.config['SESSION_COOKIE_SAMESITE'] = getattr(cfg, 'SESSION_COOKIE_SAMESITE', 'Lax')
    app.config['SESSION_COOKIE_SECURE']   = getattr(cfg, 'SESSION_COOKIE_SECURE', False)
    app.config['PERMANENT_SESSION_LIFETIME'] = cfg.PERMANENT_SESSION_LIFETIME
    app.config['MAX_CONTENT_LENGTH'] = cfg.MAX_CONTENT_LENGTH

    # Store config object on app for services that need it in threads
    app.terraria_config = cfg

    # Register blueprints
    from .blueprints.auth       import bp as auth_bp
    from .blueprints.dashboard  import bp as dashboard_bp
    from .blueprints.players    import bp as players_bp
    from .blueprints.world      import bp as world_bp
    from .blueprints.mods       import bp as mods_bp
    from .blueprints.backups    import bp as backups_bp
    from .blueprints.config_bp  import bp as config_bp
    from .blueprints.console    import bp as console_bp
    from .blueprints.api        import bp as api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(players_bp)
    app.register_blueprint(world_bp)
    app.register_blueprint(mods_bp)
    app.register_blueprint(backups_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(console_bp)
    app.register_blueprint(api_bp)

    # Security headers on every response
    @app.after_request
    def _security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        return response

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Not found', 'status': 404}), 404
        if session.get('logged_in'):
            return render_template('error.html', code=404, message='Page not found'), 404
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error', 'status': 500}), 500
        return render_template('error.html', code=500, message='Internal server error'), 500

    @app.errorhandler(413)
    def too_large(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'File too large', 'status': 413}), 413
        from flask import flash, redirect, url_for
        flash('File is too large (max 256 MB)', 'error')
        return redirect(request.referrer or url_for('dashboard.dashboard'))

    # Start background daemons only once.
    # Skip in TESTING mode (CI/pytest) to avoid Docker calls and thread leaks.
    # Guard against werkzeug reloader double-start in dev.
    if not os.environ.get('TESTING') and (
        not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    ):
        from .services.schedulers import start_all
        start_all(app)

    return app
