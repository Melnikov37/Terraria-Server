import os

from flask import Flask

from .config import Config


def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder='../templates',
    )
    cfg = config_class()
    app.secret_key = cfg.SECRET_KEY
    app.config['SESSION_COOKIE_HTTPONLY'] = cfg.SESSION_COOKIE_HTTPONLY
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

    # Start background daemons only once.
    # Skip in TESTING mode (CI/pytest) to avoid Docker calls and thread leaks.
    # Guard against werkzeug reloader double-start in dev.
    if not os.environ.get('TESTING') and (
        not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    ):
        from .services.schedulers import start_all
        start_all(app)

    return app
