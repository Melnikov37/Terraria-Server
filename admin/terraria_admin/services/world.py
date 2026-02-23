import os
import time
from datetime import datetime

import requests

from .server import get_server_type, _stored_version, container_action

# Simple in-memory cache for version info to avoid hitting GitHub on every page load.
_version_cache: dict = {}
_VERSION_CACHE_TTL = 600  # seconds (10 minutes)


def list_worlds(cfg):
    """Return list of .wld files available in WORLDS_DIR."""
    if not os.path.isdir(cfg.WORLDS_DIR):
        return []
    worlds = []
    for fname in sorted(os.listdir(cfg.WORLDS_DIR)):
        if not fname.endswith('.wld'):
            continue
        path = os.path.join(cfg.WORLDS_DIR, fname)
        worlds.append({
            'name': fname[:-4],
            'filename': fname,
            'size_mb': round(os.path.getsize(path) / (1024 * 1024), 1),
            'modified': datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M'),
        })
    return worlds


def get_version_info(cfg):
    server_type = get_server_type(cfg)
    current = _stored_version(cfg)

    # Return cached result if still fresh
    cache_key = server_type
    cached = _version_cache.get(cache_key)
    if cached and (time.monotonic() - cached['ts']) < _VERSION_CACHE_TTL:
        latest = cached['latest']
    else:
        latest = 'unknown'
        try:
            if server_type == 'tshock':
                resp = requests.get(
                    'https://api.github.com/repos/Pryaxis/TShock/releases/latest', timeout=5
                )
                if resp.ok:
                    latest = resp.json().get('tag_name', 'unknown')
            elif server_type == 'tmodloader':
                resp = requests.get(
                    'https://api.github.com/repos/tModLoader/tModLoader/releases/latest', timeout=5
                )
                if resp.ok:
                    latest = resp.json().get('tag_name', 'unknown')
            else:
                resp = requests.get(
                    'https://terraria.org/api/get/dedicated-servers-names', timeout=5
                )
                if resp.ok:
                    files = resp.json()
                    if files:
                        import re
                        match = re.search(r'(\d+)', files[0])
                        if match:
                            ver = match.group(1)
                            latest = f"1.4.5.{ver[-1]}" if len(ver) == 4 else ver
        except Exception:
            pass
        _version_cache[cache_key] = {'latest': latest, 'ts': time.monotonic()}

    return {
        'current': current,
        'latest': latest,
        'server_type': server_type,
        'update_available': current != latest and latest != 'unknown',
    }


def update_tmodloader(cfg):
    """Download and install the latest tModLoader release. Returns (success, message)."""
    import shutil
    import tempfile
    import time
    import zipfile

    try:
        resp = requests.get(
            'https://api.github.com/repos/tModLoader/tModLoader/releases/latest', timeout=10
        )
        if not resp.ok:
            return False, 'Failed to fetch release info from GitHub'

        release = resp.json()
        latest_tag = release.get('tag_name', '')
        current = _stored_version(cfg)

        if latest_tag == current:
            return True, f'tModLoader is already up to date ({current})'

        assets = release.get('assets', [])
        zip_asset = next(
            (a for a in assets
             if a['name'] == 'tModLoader.zip' or
             (a['name'].endswith('.zip') and 'source' not in a['name'].lower())),
            None
        )
        if not zip_asset:
            return False, 'Could not find tModLoader.zip in the latest GitHub release'

        tml_dir = os.path.join(cfg.TERRARIA_DIR, 'tModLoader')
        backup_dir = os.path.join(cfg.TERRARIA_DIR, f'tModLoader_bak_{current}')
        if os.path.isdir(tml_dir) and not os.path.isdir(backup_dir):
            shutil.copytree(tml_dir, backup_dir)

        try:
            container_action('stop', cfg)
        except Exception:
            pass
        time.sleep(2)

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, 'tModLoader.zip')
            r = requests.get(zip_asset['browser_download_url'], stream=True, timeout=300)
            with open(zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            shutil.rmtree(tml_dir, ignore_errors=True)
            os.makedirs(tml_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tml_dir)

        with open(os.path.join(cfg.TERRARIA_DIR, '.server_version'), 'w') as f:
            f.write(latest_tag)

        try:
            container_action('start', cfg)
        except Exception:
            pass
        return True, f'tModLoader updated: {current} → {latest_tag}. Server restarting.'

    except Exception as exc:
        return False, f'Update failed: {exc}'
