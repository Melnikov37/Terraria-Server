import logging
import time

from ..extensions import console_buffer, console_lock, ANSI_ESCAPE, MAX_CONSOLE_LINES

log = logging.getLogger(__name__)


def check_player_event(line, cfg, discord_notify_fn):
    """Detect player join/leave in a log line and fire Discord notification."""
    lower = line.lower()
    if 'has joined' in lower:
        name = line.split('has joined')[0].strip().split()[-1] if line.strip() else 'Someone'
        discord_notify_fn(f'**{name}** joined the server', cfg, color=0x3fb950, event='join')
    elif 'has left' in lower or 'has disconnected' in lower:
        key = 'has left' if 'has left' in lower else 'has disconnected'
        name = line.split(key)[0].strip().split()[-1] if line.strip() else 'Someone'
        discord_notify_fn(f'**{name}** left the server', cfg, color=0xd29922, event='leave')


def start_console_poller(app):
    """Start two daemon threads that fill console_buffer from all available sources.

    1. Docker-log poller  — streams container logs via Docker SDK (works when the
       server writes to stdout, e.g. with tty: true).
    2. File poller        — tails LOG_FILE on disk.  tModLoader writes to
       ~/.local/share/Terraria/tModLoader/Logs/server.log even in headless mode,
       so Docker logs may be empty while the file has full output.  Both pollers
       run concurrently; duplicates are harmless (they appear twice at most and
       the buffer is capped at MAX_CONSOLE_LINES).
    """
    import threading
    from ..services.discord import discord_notify

    cfg = app.terraria_config

    # ── 1. Docker-log poller ──────────────────────────────────────────────────
    def _docker_run():
        while True:
            client = None
            try:
                import docker
                client = docker.from_env()
                container = client.containers.get(cfg.SERVER_CONTAINER)
                for chunk in container.logs(
                    stream=True, follow=True, tail=200,
                    stdout=True, stderr=True,
                ):
                    chunk_text = ANSI_ESCAPE.sub(
                        '', chunk.decode('utf-8', errors='replace')
                    )
                    for line in chunk_text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        with console_lock:
                            console_buffer.append(line)
                            if len(console_buffer) > MAX_CONSOLE_LINES:
                                del console_buffer[0]
                        check_player_event(line, cfg, discord_notify)
            except Exception as exc:
                log.warning('Docker log poller error (retry in 5s): %s', exc)
            finally:
                if client:
                    try:
                        client.close()
                    except Exception:
                        pass
            time.sleep(5)

    # ── 2. File poller ────────────────────────────────────────────────────────
    def _file_run():
        import os as _os
        log_file = getattr(cfg, 'LOG_FILE', None)
        if not log_file:
            return  # LOG_FILE not configured — nothing to tail
        last_pos = 0
        while True:
            try:
                if not _os.path.exists(log_file):
                    time.sleep(2)
                    continue
                with open(log_file, 'r', errors='replace') as f:
                    # If the file was rotated / recreated, start over
                    try:
                        f.seek(last_pos)
                    except OSError:
                        f.seek(0)
                    while True:
                        raw = f.readline()
                        if not raw:
                            break
                        line = ANSI_ESCAPE.sub('', raw).strip()
                        if not line:
                            continue
                        with console_lock:
                            console_buffer.append(line)
                            if len(console_buffer) > MAX_CONSOLE_LINES:
                                del console_buffer[0]
                        check_player_event(line, cfg, discord_notify)
                    last_pos = f.tell()
            except Exception as exc:
                log.warning('File log poller error (retry in 2s): %s', exc)
                last_pos = 0
            time.sleep(0.5)

    threading.Thread(target=_docker_run, daemon=True, name='console-docker-poller').start()
    threading.Thread(target=_file_run,   daemon=True, name='console-file-poller').start()
