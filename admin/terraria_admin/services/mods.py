import json
import os
import shutil
import subprocess
import zlib
from datetime import datetime


# ------------------------------------------------------------------
# .tmod binary parser helpers
# ------------------------------------------------------------------

def _read_7bit_string(data, pos):
    """Read a .NET BinaryWriter 7-bit-encoded string from *data* at *pos*."""
    length = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        length |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    text = data[pos:pos + length].decode('utf-8', errors='replace')
    return text, pos + length


def _read_dotnet_string_list(data, pos):
    """Read a .NET BinaryWriter list of strings terminated by an empty string."""
    items = []
    while True:
        s, pos = _read_7bit_string(data, pos)
        if not s:
            break
        items.append(s)
    return items, pos


def _parse_info_binary(data):
    """Parse tModLoader binary Info file and return (mod_refs, weak_refs)."""
    STRING_VALUE_TAGS = frozenset({
        'author', 'version', 'displayName', 'homepage',
        'description', 'eacPath', 'buildVersion', 'modSource',
    })
    LIST_VALUE_TAGS = frozenset({
        'modReferences', 'weakReferences',
        'sortAfter', 'sortBefore', 'dllReferences',
    })

    pos = 0
    mod_refs = []
    weak_refs = []

    while pos < len(data):
        tag, pos = _read_7bit_string(data, pos)
        if not tag:
            break

        if tag == 'modReferences':
            refs, pos = _read_dotnet_string_list(data, pos)
            mod_refs = [r.split('@')[0] for r in refs]
        elif tag == 'weakReferences':
            refs, pos = _read_dotnet_string_list(data, pos)
            weak_refs = [r.split('@')[0] for r in refs]
        elif tag in LIST_VALUE_TAGS:
            _, pos = _read_dotnet_string_list(data, pos)
        elif tag in STRING_VALUE_TAGS:
            _, pos = _read_7bit_string(data, pos)
        elif tag == 'side':
            pos += 1

    return mod_refs, weak_refs


def _parse_tmod_file_table(raw, pos):
    """Parse mod name/version and file table from signed data section."""
    mod_name, pos = _read_7bit_string(raw, pos)
    _, pos = _read_7bit_string(raw, pos)  # mod version

    file_count = int.from_bytes(raw[pos:pos + 4], 'little')
    pos += 4

    entries = []
    running_offset = 0
    for _ in range(file_count):
        name, pos = _read_7bit_string(raw, pos)
        u_len = int.from_bytes(raw[pos:pos + 4], 'little'); pos += 4
        c_len = int.from_bytes(raw[pos:pos + 4], 'little'); pos += 4
        entries.append((name, running_offset, u_len, c_len))
        running_offset += c_len

    file_data_start = pos
    return mod_name, entries, file_data_start


def parse_tmod_dependencies(tmod_path):
    """Return list of hard-required mod names from the Info file inside a .tmod."""
    try:
        with open(tmod_path, 'rb') as fh:
            raw = fh.read()

        if raw[:4] != b'TMOD':
            return []

        pos = 4
        _, pos = _read_7bit_string(raw, pos)  # tML version
        pos += 20 + 256 + 4                   # hash + sig + datalen

        _, entries, file_data_start = _parse_tmod_file_table(raw, pos)

        for name, offset, u_len, c_len in entries:
            if name == 'Info':
                start = file_data_start + offset
                file_bytes = raw[start:start + c_len]
                if u_len != c_len:
                    file_bytes = zlib.decompress(file_bytes, wbits=-15)
                mod_refs, _ = _parse_info_binary(file_bytes)
                return mod_refs

        for name, offset, u_len, c_len in entries:
            if name == 'build.txt':
                start = file_data_start + offset
                file_bytes = raw[start:start + c_len]
                if u_len != c_len:
                    file_bytes = zlib.decompress(file_bytes, wbits=-15)
                for line in file_bytes.decode('utf-8', errors='replace').splitlines():
                    line = line.strip()
                    if line.startswith('modReferences') and '=' in line:
                        return [d.strip() for d in line.split('=', 1)[1].split(',') if d.strip()]
                return []

    except Exception:
        pass
    return []


def extract_tmod_version(tmod_path):
    """Read mod name and version from .tmod header."""
    with open(tmod_path, 'rb') as fh:
        raw = fh.read(2048)  # 512 was too small for mods with long names/versions
    pos = 4
    _, pos = _read_7bit_string(raw, pos)   # tML version
    pos += 20 + 256 + 4                    # hash + sig + datalen
    mod_name, pos = _read_7bit_string(raw, pos)
    mod_version, _ = _read_7bit_string(raw, pos)
    return mod_name, mod_version


# ------------------------------------------------------------------
# enabled.json helpers
# ------------------------------------------------------------------

def get_enabled_mods(cfg):
    """Return dict {ModName: bool} regardless of enabled.json format."""
    enabled_file = os.path.join(cfg.MODS_DIR, 'enabled.json')
    if os.path.exists(enabled_file):
        try:
            with open(enabled_file) as f:
                data = json.load(f)
            if isinstance(data, list):
                return {name: True for name in data}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_enabled_mods(enabled, cfg):
    """Write enabled.json in tModLoader's native list format."""
    os.makedirs(cfg.MODS_DIR, exist_ok=True)
    enabled_file = os.path.join(cfg.MODS_DIR, 'enabled.json')
    enabled_list = [name for name, active in enabled.items() if active]
    with open(enabled_file, 'w') as f:
        json.dump(enabled_list, f, indent=2)


# ------------------------------------------------------------------
# Mod metadata cache
# ------------------------------------------------------------------

def _meta_file(cfg):
    return os.path.join(cfg.MODS_DIR, '.mod_meta.json')


def get_mod_meta(cfg):
    path = _meta_file(cfg)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_mod_meta(meta, cfg):
    os.makedirs(cfg.MODS_DIR, exist_ok=True)
    with open(_meta_file(cfg), 'w') as f:
        json.dump(meta, f, indent=2)


def record_mod_installed(mod_name, tmod_path, cfg, workshop_id=None):
    """Update metadata cache after a mod is installed or updated."""
    meta = get_mod_meta(cfg)
    try:
        _, version = extract_tmod_version(tmod_path)
    except Exception:
        version = 'unknown'
    now = datetime.now().isoformat(timespec='seconds')
    entry = meta.get(mod_name, {})
    entry['version'] = version
    entry['last_updated'] = now
    if 'installed_at' not in entry:
        entry['installed_at'] = now
    if workshop_id:
        entry['workshop_id'] = workshop_id
    meta[mod_name] = entry
    save_mod_meta(meta, cfg)


def remove_mod_meta(mod_name, cfg):
    meta = get_mod_meta(cfg)
    if mod_name in meta:
        meta.pop(mod_name)
        save_mod_meta(meta, cfg)


# ------------------------------------------------------------------
# List mods
# ------------------------------------------------------------------

def list_mods(cfg):
    """Scan MODS_DIR for .tmod files and return metadata list."""
    mods = []
    if not os.path.isdir(cfg.MODS_DIR):
        return mods

    enabled = get_enabled_mods(cfg)
    meta = get_mod_meta(cfg)

    for fname in sorted(os.listdir(cfg.MODS_DIR)):
        if not fname.endswith('.tmod'):
            continue
        mod_name = fname[:-5]
        fpath = os.path.join(cfg.MODS_DIR, fname)
        size_bytes = os.path.getsize(fpath)
        mod_meta = meta.get(mod_name, {})
        workshop_id = mod_meta.get('workshop_id') or cfg.KNOWN_WORKSHOP_IDS.get(mod_name)
        mods.append({
            'name': mod_name,
            'filename': fname,
            'enabled': enabled.get(mod_name, False),
            'size_mb': round(size_bytes / (1024 * 1024), 2),
            'version': mod_meta.get('version', '?'),
            'workshop_id': workshop_id,
            'last_updated': mod_meta.get('last_updated', ''),
        })

    return mods


# ------------------------------------------------------------------
# steamcmd download helper
# ------------------------------------------------------------------

def download_mod_from_workshop(steamcmd, workshop_id, cfg):
    """Download a Workshop item and copy the .tmod into MODS_DIR."""
    steamcmd_home = '/tmp/steamcmd_home'
    os.makedirs(steamcmd_home, exist_ok=True)
    try:
        result = subprocess.run(
            [steamcmd,
             '+login', 'anonymous',
             '+workshop_download_item', cfg.TERRARIA_APP_ID, workshop_id,
             '+quit'],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, 'HOME': steamcmd_home}
        )

        workshop_dir = os.path.join(
            steamcmd_home, 'Steam', 'steamapps', 'workshop',
            'content', cfg.TERRARIA_APP_ID, workshop_id
        )
        # Some steamcmd versions store tModLoader mods under App ID 1281930 instead of 105600
        if not os.path.isdir(workshop_dir):
            workshop_dir = os.path.join(
                steamcmd_home, 'Steam', 'steamapps', 'workshop',
                'content', '1281930', workshop_id
            )

        if not os.path.isdir(workshop_dir):
            tail = (result.stdout + result.stderr)[-600:]
            return None, f'Workshop item {workshop_id} download failed. steamcmd: {tail}'

        tmod_files = [
            os.path.join(root, f)
            for root, _, files in os.walk(workshop_dir)
            for f in files if f.endswith('.tmod')
        ]

        if not tmod_files:
            return None, f'No .tmod file found in Workshop item {workshop_id}'

        def _tmod_version_key(path):
            dirname = os.path.basename(os.path.dirname(path))
            try:
                return [int(x) for x in dirname.split('.')]
            except (ValueError, AttributeError):
                return [0]

        tmod_file = max(tmod_files, key=_tmod_version_key)
        os.makedirs(cfg.MODS_DIR, exist_ok=True)
        dest = os.path.join(cfg.MODS_DIR, os.path.basename(tmod_file))
        shutil.copy2(tmod_file, dest)
        mod_name = os.path.basename(tmod_file)[:-5]
        return mod_name, None

    except subprocess.TimeoutExpired:
        return None, f'Download of Workshop item {workshop_id} timed out (5 min)'
    except Exception as exc:
        return None, f'Error downloading Workshop item {workshop_id}: {exc}'


# ------------------------------------------------------------------
# Dependency auto-installer
# ------------------------------------------------------------------

def ensure_mod_dependencies(tmod_path, steamcmd, cfg):
    """Parse tmod_path for modReferences and auto-install any that are missing."""
    messages = []
    deps = parse_tmod_dependencies(tmod_path)
    if not deps:
        return messages

    for dep in deps:
        dep_file = os.path.join(cfg.MODS_DIR, f'{dep}.tmod')

        if os.path.exists(dep_file):
            enabled = get_enabled_mods(cfg)
            if not enabled.get(dep, False):
                enabled[dep] = True
                save_enabled_mods(enabled, cfg)
                messages.append((True, f'Dependency "{dep}" already installed — enabled it.'))
            continue

        workshop_id = cfg.KNOWN_WORKSHOP_IDS.get(dep)
        if not workshop_id:
            messages.append((
                False,
                f'Dependency "{dep}" is required but its Workshop ID is unknown. '
                f'Install it manually and re-enable the mod.'
            ))
            continue

        mod_name, err = download_mod_from_workshop(steamcmd, workshop_id, cfg)
        if err:
            messages.append((False, f'Failed to auto-install dependency "{dep}": {err}'))
        else:
            enabled = get_enabled_mods(cfg)
            enabled[mod_name] = True
            save_enabled_mods(enabled, cfg)
            messages.append((True, f'Auto-installed dependency "{dep}" (Workshop {workshop_id}).'))

    return messages


def run_background_mod_updates(cfg):
    """Re-download all Workshop mods silently."""
    steamcmd = cfg.STEAMCMD_BIN if os.path.exists(cfg.STEAMCMD_BIN) else shutil.which('steamcmd')
    if not steamcmd:
        return

    for mod in list_mods(cfg):
        mod_name = mod['name']
        workshop_id = mod.get('workshop_id')
        if not workshop_id:
            continue
        try:
            new_mod_name, err = download_mod_from_workshop(steamcmd, workshop_id, cfg)
            if not err:
                dest = os.path.join(cfg.MODS_DIR, f'{new_mod_name}.tmod')
                record_mod_installed(new_mod_name, dest, cfg, workshop_id)
        except Exception:
            pass
