import time
import threading


def start_all(app):
    """Start all daemon background threads."""
    from .console import start_console_poller
    from .backups import create_backup, prune_auto_backups
    from .mods    import run_background_mod_updates

    cfg = app.terraria_config

    start_console_poller(app)

    if cfg.AUTO_BACKUP_INTERVAL_HOURS > 0:
        def _backup_loop():
            while True:
                time.sleep(cfg.AUTO_BACKUP_INTERVAL_HOURS * 3600)
                try:
                    with app.app_context():
                        create_backup(cfg, 'auto')
                        prune_auto_backups(cfg)
                except Exception:
                    pass

        threading.Thread(target=_backup_loop, daemon=True, name='auto-backup').start()

    if cfg.MOD_UPDATE_INTERVAL_HOURS > 0:
        def _mod_loop():
            while True:
                time.sleep(cfg.MOD_UPDATE_INTERVAL_HOURS * 3600)
                try:
                    run_background_mod_updates(cfg)
                except Exception:
                    pass

        threading.Thread(target=_mod_loop, daemon=True, name='mod-updater').start()
