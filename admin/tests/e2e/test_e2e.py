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
