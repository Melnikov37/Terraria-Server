"""
End-to-end browser tests using Playwright.

These tests run a real browser against a live Flask server.
Mark: @pytest.mark.e2e
Run with: pytest -m e2e [--headed]
"""
import re
import json
import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e


# ── Helpers ───────────────────────────────────────────────────────────────────

def login(page: Page, base_url: str, token: str) -> None:
    page.goto(f'{base_url}/login')
    page.fill('input[name="token"]', token)
    page.click('button[type="submit"]')
    page.wait_for_url(f'{base_url}/')


def wait_for_toast(page: Page, text: str, timeout: int = 5000) -> None:
    """Wait for a toast notification containing *text* to appear."""
    page.wait_for_selector(f'.toast-body', timeout=timeout)
    expect(page.locator('.toast-body').first).to_contain_text(text)


# ── Auth flow ─────────────────────────────────────────────────────────────────

def test_login_page_loads(page: Page, base_url: str):
    page.goto(f'{base_url}/login')
    # Use regex — Playwright doesn't accept callables for to_have_title
    expect(page).to_have_title(re.compile(r'Login|Terraria'))
    expect(page.locator('input[name="token"]')).to_be_visible()


def test_login_with_wrong_token_shows_error(page: Page, base_url: str):
    page.goto(f'{base_url}/login')
    page.fill('input[name="token"]', 'wrong-token')
    page.click('button[type="submit"]')
    # Flash message is rendered as a JS toast in .toast-body
    wait_for_toast(page, 'Invalid token')


def test_login_success_redirects_to_dashboard(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    expect(page).to_have_url(f'{base_url}/')


def test_unauthenticated_access_redirects_to_login(page: Page, base_url: str):
    page.goto(f'{base_url}/')
    # Use regex — Playwright doesn't accept callables for to_have_url
    expect(page).to_have_url(re.compile(r'/login'))


def test_logout_redirects_to_login(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/logout')
    expect(page).to_have_url(re.compile(r'/login'))


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_shows_server_status(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    expect(page.locator('body')).to_contain_text('Terraria')


def test_dashboard_has_server_controls(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    # Look specifically for submit buttons inside server control forms
    # (not the hamburger mobile toggle button which is display:none on desktop)
    controls = page.locator('button[type="submit"]')
    expect(controls.first).to_be_visible()


# ── Navigation sidebar ────────────────────────────────────────────────────────

def test_nav_links_present(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    for href in ('/backups', '/mods', '/players', '/world', '/console', '/logs'):
        link = page.locator(f'a[href="{href}"]')
        expect(link.first).to_be_visible()


def test_navigate_to_backups(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.click('a[href="/backups"]')
    expect(page).to_have_url(f'{base_url}/backups')
    expect(page.locator('body')).to_contain_text('Backup')


def test_navigate_to_mods(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.click('a[href="/mods"]')
    expect(page).to_have_url(f'{base_url}/mods')
    expect(page.locator('body')).to_contain_text('Mod')


def test_navigate_to_players(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.click('a[href="/players"]')
    expect(page).to_have_url(f'{base_url}/players')
    expect(page.locator('body')).to_contain_text('Player')


def test_navigate_to_world(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.click('a[href="/world"]')
    expect(page).to_have_url(f'{base_url}/world')
    expect(page.locator('body')).to_contain_text('World')


def test_navigate_to_console(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.click('a[href="/console"]')
    expect(page).to_have_url(f'{base_url}/console')
    expect(page.locator('body')).to_contain_text('Console')


# ── Backups ───────────────────────────────────────────────────────────────────

def test_backups_page_shows_create_button(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/backups')
    # Use button:has-text() to avoid strict-mode violation from text= matching
    # the button element AND a nested text node
    expect(page.locator('button:has-text("Create Backup Now")')).to_be_visible()


def test_create_backup_flow(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/backups')
    page.locator('button:has-text("Create Backup Now")').click()
    # After redirect, a flash toast should appear (success or error)
    page.wait_for_url(f'{base_url}/backups')
    expect(page.locator('body')).to_contain_text('Backup')


# ── Mods public ───────────────────────────────────────────────────────────────

def test_mods_public_accessible_without_login(page: Page, base_url: str):
    page.goto(f'{base_url}/mods/public')
    assert page.url == f'{base_url}/mods/public'


# ── World commands ────────────────────────────────────────────────────────────

def test_broadcast_empty_message_shows_error(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    broadcast_form = page.locator('form[action*="broadcast"]')
    if broadcast_form.count() > 0:
        broadcast_form.locator('input[name="message"]').fill('')
        broadcast_form.locator('button[type="submit"]').click()
        wait_for_toast(page, 'cannot be empty')


# ── API JSON endpoints ────────────────────────────────────────────────────────

def test_api_status_returns_json(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    response = page.request.get(f'{base_url}/api/status')
    assert response.status == 200
    data = response.json()
    assert 'online' in data


def test_api_logs_returns_json(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    response = page.request.get(f'{base_url}/api/logs?lines=50')
    assert response.status == 200
    data = response.json()
    assert 'lines' in data
    assert isinstance(data['lines'], list)


def test_api_console_send_via_http(page: Page, base_url: str, admin_token: str):
    login(page, base_url, admin_token)
    response = page.request.post(
        f'{base_url}/api/console/send',
        data=json.dumps({'cmd': 'help'}),
        headers={'Content-Type': 'application/json'},
    )
    assert response.status == 200
    data = response.json()
    assert 'ok' in data


# ── World page ────────────────────────────────────────────────────────────────

def test_world_page_shows_worlds_card(page: Page, base_url: str, admin_token: str):
    """Worlds card header must be visible."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    expect(page.locator('body')).to_contain_text('Worlds')


def test_world_list_shows_existing_world(page: Page, base_url: str, admin_token: str):
    """E2EWorld.wld from the fixture must appear in the world list."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    expect(page.locator('body')).to_contain_text('E2EWorld')


def test_world_list_shows_file_size(page: Page, base_url: str, admin_token: str):
    """Each world row must display its size in MB."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    expect(page.locator('body')).to_contain_text('MB')


def test_world_list_shows_modification_date(page: Page, base_url: str, admin_token: str):
    """Each world row must display the last-modified date."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    # Date is formatted as YYYY-MM-DD HH:MM
    import re as _re
    content = page.locator('body').inner_text()
    assert _re.search(r'\d{4}-\d{2}-\d{2}', content), 'Expected a date in YYYY-MM-DD format'


def test_world_list_inactive_world_has_switch_button(page: Page, base_url: str, admin_token: str):
    """E2EWorld is not the active world so it must show a Switch & Restart button."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    expect(page.locator('button:has-text("Switch")')).to_be_visible()


def test_world_list_active_world_shows_active_badge(page: Page, base_url: str, admin_token: str):
    """When a world matches the configured worldname it must show the Active badge."""
    login(page, base_url, admin_token)
    # Write a serverconfig that names E2EWorld as the current world so the
    # badge logic can be tested end-to-end (status.world == 'E2EWorld').
    import os as _os
    from terraria_admin.config import Config
    terraria_dir = _os.environ.get('TERRARIA_DIR', '/tmp')
    cfg_path = _os.path.join(terraria_dir, 'serverconfig.txt')
    with open(cfg_path, 'w') as fh:
        fh.write('worldname=E2EWorld\n')
    try:
        page.goto(f'{base_url}/world')
        expect(page.locator('body')).to_contain_text('Active')
    finally:
        _os.remove(cfg_path)


def test_world_switch_triggers_confirm_dialog(page: Page, base_url: str, admin_token: str):
    """Clicking Switch must show a browser confirm dialog before submitting."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    # Dismiss the dialog — the form must NOT submit
    page.on('dialog', lambda d: d.dismiss())
    switch_btn = page.locator('button:has-text("Switch")')
    if switch_btn.count() > 0:
        switch_btn.first.click()
        expect(page).to_have_url(f'{base_url}/world')


def test_world_create_form_has_required_fields(page: Page, base_url: str, admin_token: str):
    """Create New World form must expose all tModLoader options."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    expect(page.locator('input[name="worldname"]')).to_be_visible()
    expect(page.locator('select[name="size"]')).to_be_visible()
    expect(page.locator('select[name="difficulty"]')).to_be_visible()
    expect(page.locator('select[name="evil"]')).to_be_visible()
    expect(page.locator('input[name="seed"]')).to_be_visible()


# ── Console page ──────────────────────────────────────────────────────────────

def test_console_page_has_output_area(page: Page, base_url: str, admin_token: str):
    """Console page must have a scrollable #output div."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/console')
    expect(page.locator('#output')).to_be_visible()


def test_console_page_has_command_input(page: Page, base_url: str, admin_token: str):
    """Console page must have a command input field and Send button."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/console')
    expect(page.locator('#cmdInput')).to_be_visible()
    expect(page.locator('button:has-text("Send")')).to_be_visible()


def test_console_page_has_follow_toggle(page: Page, base_url: str, admin_token: str):
    """Console page must have a Follow ON/OFF toggle button."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/console')
    expect(page.locator('#btnFollow')).to_be_visible()


def test_console_api_lines_returns_valid_structure(page: Page, base_url: str, admin_token: str):
    """GET /api/console/lines must return {lines: [...], total: N}."""
    login(page, base_url, admin_token)
    response = page.request.get(f'{base_url}/api/console/lines?since=0')
    assert response.status == 200
    data = response.json()
    assert 'lines' in data
    assert 'total' in data
    assert isinstance(data['lines'], list)
    assert isinstance(data['total'], int)


def test_console_api_since_param_filters(page: Page, base_url: str, admin_token: str):
    """since=9999 must return an empty lines list without error."""
    login(page, base_url, admin_token)
    response = page.request.get(f'{base_url}/api/console/lines?since=9999999')
    assert response.status == 200
    data = response.json()
    assert data['lines'] == []


def test_console_send_empty_returns_error(page: Page, base_url: str, admin_token: str):
    """POSTing a blank cmd must return ok=False with an error message."""
    login(page, base_url, admin_token)
    response = page.request.post(
        f'{base_url}/api/console/send',
        data=json.dumps({'cmd': '   '}),
        headers={'Content-Type': 'application/json'},
    )
    assert response.status == 200
    data = response.json()
    assert data['ok'] is False
    assert 'error' in data


def test_console_enter_key_sends_command(page: Page, base_url: str, admin_token: str):
    """Pressing Enter in the command input must submit the command."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/console')
    # Type a command and press Enter; the field should clear on success
    page.fill('#cmdInput', 'save')
    with page.expect_request('**/api/console/send') as req_info:
        page.keyboard.press('Enter')
    assert req_info.value.method == 'POST'


# ── Logs page ─────────────────────────────────────────────────────────────────

def test_logs_page_loads(page: Page, base_url: str, admin_token: str):
    """Logs page must render with a 200 status."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/logs')
    expect(page.locator('body')).to_contain_text('Logs')


def test_logs_page_has_output_element(page: Page, base_url: str, admin_token: str):
    """Logs page must render the <pre id='logOutput'> element."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/logs')
    expect(page.locator('#logOutput')).to_be_visible()


def test_logs_page_has_filter_controls(page: Page, base_url: str, admin_token: str):
    """Logs page must have level filter and line-count selects."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/logs')
    expect(page.locator('#levelFilter')).to_be_visible()
    expect(page.locator('#lineCount')).to_be_visible()


def test_logs_api_returns_valid_structure(page: Page, base_url: str, admin_token: str):
    """GET /api/logs?lines=50 must return {lines: [...]}."""
    login(page, base_url, admin_token)
    response = page.request.get(f'{base_url}/api/logs?lines=50')
    assert response.status == 200
    data = response.json()
    assert 'lines' in data
    assert isinstance(data['lines'], list)


def test_logs_api_level_filter_accepted(page: Page, base_url: str, admin_token: str):
    """level=error filter must not crash the endpoint."""
    login(page, base_url, admin_token)
    for level in ('all', 'warn', 'error'):
        response = page.request.get(f'{base_url}/api/logs?lines=50&level={level}')
        assert response.status == 200, f'level={level} returned {response.status}'
        assert 'lines' in response.json()


def test_logs_refresh_button_reloads_content(page: Page, base_url: str, admin_token: str):
    """Clicking Refresh must issue a GET request to /api/logs."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/logs')
    page.wait_for_load_state('networkidle')
    with page.expect_request('**/api/logs**') as req_info:
        page.locator('button:has-text("Refresh")').click()
    assert req_info.value.method == 'GET'


# ── Security checks ───────────────────────────────────────────────────────────

def test_xss_in_flash_message_not_executed(page: Page, base_url: str, admin_token: str):
    """Verify player names with HTML do not execute script tags in flash messages."""
    login(page, base_url, admin_token)
    page.goto(f'{base_url}/world')
    broadcast_form = page.locator('form[action*="broadcast"]')
    if broadcast_form.count() > 0:
        broadcast_form.locator('input[name="message"]').fill('<script>window._xss=1</script>')
        broadcast_form.locator('button[type="submit"]').click()
        # Script should not have executed
        xss_value = page.evaluate('window._xss')
        assert xss_value is None
