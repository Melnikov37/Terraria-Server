from flask import Blueprint, current_app, jsonify, render_template, request

from ..decorators import login_required
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
    since = max(0, min(since, len(buf)))
    return jsonify({'lines': buf[since:], 'total': len(buf)})


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
