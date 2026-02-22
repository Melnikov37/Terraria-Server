import os
import time


def _fifo_path(cfg):
    return os.path.join(cfg.TERRARIA_DIR, '.server-input')


def screen_send(cmd, cfg):
    """Write a command to the server's stdin FIFO."""
    try:
        fifo = _fifo_path(cfg)
        with open(fifo, 'w') as f:
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
    try:
        import docker
        client = docker.from_env()
        container = client.containers.get(cfg.SERVER_CONTAINER)
        return container.status == 'running'
    except Exception:
        return False


def screen_cmd_output(cmd, cfg, wait=0.8):
    """Send cmd to server stdin, wait, return lines added to console buffer since then."""
    from ..extensions import console_buffer
    before_len = len(console_buffer)
    screen_send(cmd, cfg)
    time.sleep(wait)
    new_lines = list(console_buffer)[before_len:]
    return '\n'.join(new_lines)
