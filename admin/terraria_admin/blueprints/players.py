from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..decorators import login_required
from ..services.server import get_players, get_server_type
from ..services.tshock import rest_call
from ..services.screen import screen_send

bp = Blueprint('players', __name__)


@bp.route('/players')
@login_required
def players():
    cfg = current_app.terraria_config
    player_list = get_players(cfg)
    bans = []
    if get_server_type(cfg) == 'tshock':
        bans_result = rest_call('/v2/bans/list', cfg)
        bans = bans_result.get('bans', []) if bans_result.get('status') == '200' else []
    return render_template('players.html', players=player_list, bans=bans)


@bp.route('/players/kick', methods=['POST'])
@login_required
def kick_player():
    cfg = current_app.terraria_config
    player = request.form.get('player', '').strip()[:100]
    reason = request.form.get('reason', 'Kicked by admin').strip()[:300] or 'Kicked by admin'
    if not player:
        flash('Player name is required', 'error')
        return redirect(url_for('players.players'))

    server_type = get_server_type(cfg)
    if server_type == 'tshock':
        result = rest_call('/v2/players/kick', cfg, 'POST', {'player': player, 'reason': reason})
        if result.get('status') == '200':
            flash(f'Kicked {player}', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send(f'kick {player}', cfg)
        flash(f'Kick command sent for {player}', 'success')

    return redirect(url_for('players.players'))


@bp.route('/players/ban', methods=['POST'])
@login_required
def ban_player():
    cfg = current_app.terraria_config
    player = request.form.get('player', '').strip()[:100]
    reason = request.form.get('reason', 'Banned by admin').strip()[:300] or 'Banned by admin'
    if not player:
        flash('Player name is required', 'error')
        return redirect(url_for('players.players'))

    server_type = get_server_type(cfg)
    if server_type == 'tshock':
        result = rest_call('/v2/bans/create', cfg, 'POST', {
            'name': player, 'reason': reason, 'type': 'name'
        })
        if result.get('status') == '200':
            flash(f'Banned {player}', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        screen_send(f'ban {player}', cfg)
        flash(f'Ban command sent for {player}', 'success')

    return redirect(url_for('players.players'))


@bp.route('/players/unban', methods=['POST'])
@login_required
def unban_player():
    cfg = current_app.terraria_config
    ban_id = request.form.get('id')
    if get_server_type(cfg) == 'tshock':
        result = rest_call('/v2/bans/destroy', cfg, 'POST', {'id': ban_id})
        if result.get('status') == '200':
            flash('Ban removed', 'success')
        else:
            flash(f'Error: {result.get("error", "Unknown")}', 'error')
    else:
        flash('Unban via ID is only available for TShock servers', 'error')
    return redirect(url_for('players.players'))
