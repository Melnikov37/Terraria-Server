import re
import threading
from collections import deque

# Live console buffer — filled by the background log pollers.
# Shared between background thread (writer) and Flask routes (readers).
# deque(maxlen=...) gives O(1) append + automatic eviction of the oldest entry,
# replacing the previous plain-list approach that required an O(n) del [0].
MAX_CONSOLE_LINES = 500
console_buffer: deque = deque(maxlen=MAX_CONSOLE_LINES)
console_lock = threading.Lock()
# Monotonically increasing counter: total lines ever appended to console_buffer.
# When the buffer is full and a line is evicted from the front, this counter
# keeps growing so the JS cursor (since=N) always points to the right offset
# even after old lines have been removed.
console_seq: int = 0
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
