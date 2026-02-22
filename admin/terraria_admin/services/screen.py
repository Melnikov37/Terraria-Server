import os
import subprocess
import tempfile
import time


def screen_send(cmd, cfg):
    """Send a command to the server via screen."""
    try:
        subprocess.run(
            ['screen', '-S', cfg.SCREEN_SESSION, '-X', 'stuff', f'{cmd}\r'],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        return False


def screen_capture(cfg, wait=0.6):
    """Read current screen terminal contents."""
    try:
        tmpfile = tempfile.mktemp(suffix='.txt', prefix='tserver_')
        time.sleep(wait)
        subprocess.run(
            ['screen', '-S', cfg.SCREEN_SESSION, '-p', '0', '-X', 'hardcopy', '-h', tmpfile],
            capture_output=True, timeout=5
        )
        if os.path.exists(tmpfile):
            with open(tmpfile, 'r', errors='ignore') as f:
                content = f.read()
            try:
                os.unlink(tmpfile)
            except OSError:
                pass
            return content
    except Exception:
        pass
    return ''


def is_screen_running(cfg):
    """Check whether a screen session named SCREEN_SESSION exists."""
    try:
        result = subprocess.run(
            ['screen', '-ls'], capture_output=True, text=True, timeout=5
        )
        return cfg.SCREEN_SESSION in result.stdout
    except Exception:
        return False


def screen_cmd_output(cmd, cfg, wait=0.8):
    """Send cmd, wait, return screen output."""
    screen_send(cmd, cfg)
    return screen_capture(cfg, wait=wait)
