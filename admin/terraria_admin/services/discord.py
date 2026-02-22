import json
import os
import threading
from datetime import datetime

import requests


def get_discord_config(cfg):
    if os.path.exists(cfg.DISCORD_CONFIG_FILE):
        try:
            with open(cfg.DISCORD_CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_discord_config(data, cfg):
    with open(cfg.DISCORD_CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def discord_notify(message, cfg, color=0x3fb950, event='info'):
    """Fire-and-forget Discord webhook notification in a background thread."""
    dcfg = get_discord_config(cfg)
    webhook_url = dcfg.get('webhook_url', '').strip()
    if not webhook_url:
        return
    if not dcfg.get(f'notify_{event}', True):
        return

    def _send():
        try:
            requests.post(webhook_url, json={
                'embeds': [{
                    'description': message,
                    'color': color,
                    'footer': {'text': 'Terraria Server'},
                    'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                }]
            }, timeout=5)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True, name='discord-notify').start()
