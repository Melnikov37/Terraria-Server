import re
import threading

# Live console buffer — filled by the background journalctl poller.
# Shared between background thread (writer) and Flask routes (readers).
MAX_CONSOLE_LINES = 500
console_buffer: list = []
console_lock = threading.Lock()
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
