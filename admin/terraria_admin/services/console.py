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
    """Daemon thread: stream Docker container logs and fill console_buffer."""
    import threading
    from ..services.discord import discord_notify

    cfg = app.terraria_config

    def _run():
        import docker
        client = docker.from_env()
        while True:
            try:
                container = client.containers.get(cfg.SERVER_CONTAINER)
                for raw_line in container.logs(stream=True, follow=True, tail=100):
                    line = ANSI_ESCAPE.sub(
                        '', raw_line.decode('utf-8', errors='replace').rstrip()
                    )
                    if not line:
                        continue
                    with console_lock:
                        console_buffer.append(line)
                        if len(console_buffer) > MAX_CONSOLE_LINES:
                            del console_buffer[0]
                    check_player_event(line, cfg, discord_notify)
            except Exception as exc:
                log.warning('Console poller error (retry in 5s): %s', exc)
                try:
                    client.close()
                except Exception:
                    pass
                time.sleep(5)
                client = docker.from_env()

    threading.Thread(target=_run, daemon=True, name='console-poller').start()
