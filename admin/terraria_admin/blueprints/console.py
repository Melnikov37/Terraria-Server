from flask import Blueprint, current_app, jsonify, render_template, request

from ..decorators import login_required
from .. import extensions
from ..extensions import console_buffer, console_lock
from ..services.server import get_server_type
from ..services.screen import screen_send

bp = Blueprint('console', __name__)


@bp.route('/console')
@login_required
def console():
    cfg = current_app.terraria_config
    return render_template('console.html', server_type=get_server_type(cfg))


@bp.route('/api/console/lines')
@login_required
def api_console_lines():
    since = int(request.args.get('since', 0))
    with console_lock:
        buf = list(console_buffer)
        seq = extensions.console_seq
    # seq is the total number of lines ever appended.
    # The buffer holds the last len(buf) lines, so their sequence numbers
    # run from (seq - len(buf)) to (seq - 1).
    buf_start = seq - len(buf)
    since = max(buf_start, min(since, seq))
    offset = since - buf_start
    return jsonify({'lines': buf[offset:], 'total': seq})


@bp.route('/api/console/send', methods=['POST'])
@login_required
def api_console_send():
    cfg = current_app.terraria_config
    data = request.get_json(silent=True) or {}
    cmd = data.get('cmd', '').strip()
    if not cmd:
        return jsonify({'ok': False, 'error': 'Empty command'})
    screen_send(cmd, cfg)
    return jsonify({'ok': True})
