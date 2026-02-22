import os
import shutil
from datetime import datetime


def create_backup(cfg, label='manual'):
    """Copy all .wld files to backups/<label>_<timestamp>/. Returns (name, error)."""
    if not os.path.isdir(cfg.WORLDS_DIR):
        return None, 'Worlds directory not found'
    wld_files = [f for f in os.listdir(cfg.WORLDS_DIR) if f.endswith('.wld')]
    if not wld_files:
        return None, 'No .wld files found in worlds directory'
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'{label}_{ts}'
    backup_path = os.path.join(cfg.BACKUPS_DIR, backup_name)
    os.makedirs(backup_path, exist_ok=True)
    for fname in wld_files:
        shutil.copy2(
            os.path.join(cfg.WORLDS_DIR, fname),
            os.path.join(backup_path, fname)
        )
    return backup_name, None


def list_backups(cfg):
    """Return list of backup dicts sorted newest-first."""
    if not os.path.isdir(cfg.BACKUPS_DIR):
        return []
    backups = []
    for name in os.listdir(cfg.BACKUPS_DIR):
        path = os.path.join(cfg.BACKUPS_DIR, name)
        if not os.path.isdir(path):
            continue
        files = [f for f in os.listdir(path) if f.endswith('.wld')]
        if not files:
            continue
        total_size = sum(os.path.getsize(os.path.join(path, f)) for f in files)
        mtime = os.path.getmtime(path)
        backups.append({
            'name': name,
            'label': 'auto' if name.startswith('auto_') else 'manual',
            'files': files,
            'size_mb': round(total_size / (1024 * 1024), 1),
            'timestamp': datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'mtime': mtime,
        })
    return sorted(backups, key=lambda b: b['mtime'], reverse=True)


def prune_auto_backups(cfg):
    """Delete oldest auto-backups beyond BACKUP_KEEP_COUNT."""
    auto = [b for b in list_backups(cfg) if b['label'] == 'auto']
    for b in auto[cfg.BACKUP_KEEP_COUNT:]:
        shutil.rmtree(os.path.join(cfg.BACKUPS_DIR, b['name']), ignore_errors=True)
