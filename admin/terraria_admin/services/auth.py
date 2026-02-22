import json
import os
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash


def get_admins(cfg):
    if os.path.exists(cfg.ADMINS_FILE):
        try:
            with open(cfg.ADMINS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_admins(admins, cfg):
    os.makedirs(os.path.dirname(cfg.ADMINS_FILE), exist_ok=True)
    with open(cfg.ADMINS_FILE, 'w') as f:
        json.dump(admins, f, indent=2)
    try:
        os.chmod(cfg.ADMINS_FILE, 0o600)
    except Exception:
        pass


def bootstrap_admins(cfg):
    """Create initial superadmin from env vars if admins file does not exist."""
    if os.path.exists(cfg.ADMINS_FILE):
        return
    save_admins(
        {
            cfg.ADMIN_USERNAME: {
                'password_hash': generate_password_hash(cfg.ADMIN_PASSWORD),
                'role': 'superadmin',
                'created_at': datetime.now().isoformat(timespec='seconds'),
            }
        },
        cfg,
    )
