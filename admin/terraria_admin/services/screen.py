import os
import time


def _fifo_path(cfg):
    return os.path.join(cfg.TERRARIA_DIR, '.server-input')


def screen_send(cmd, cfg):
    """Write a command to the server's stdin FIFO (non-blocking)."""
    fifo = _fifo_path(cfg)
    try:
        # O_NONBLOCK prevents blocking when the server is not running
        # (no reader on the other end of the FIFO).
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        with os.fdopen(fd, 'w') as f:
            f.write(cmd + '\n')
        return True
    except Exception:
        return False


def screen_capture(cfg, wait=0.6):
    """Return recent server output from the in-memory console buffer."""
    from ..extensions import console_buffer
    time.sleep(wait)
    return '\n'.join(list(console_buffer)[-80:])


def is_screen_running(cfg):
    """Check whether the terraria server container is running."""
    import docker
    client = docker.from_env()
    try:
        container = client.containers.get(cfg.SERVER_CONTAINER)
        return container.status == 'running'
    except Exception:
        return False
    finally:
        client.close()


def screen_cmd_output(cmd, cfg, wait=0.8):
    """Send cmd to server stdin, wait, return lines added to console buffer since then."""
    from ..extensions import console_buffer, console_lock
    with console_lock:
        before_len = len(console_buffer)
    if not screen_send(cmd, cfg):
        return ''
    time.sleep(wait)
    with console_lock:
        new_lines = list(console_buffer)[before_len:]
    return '\n'.join(new_lines)
