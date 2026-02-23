"""Tests for /login and /logout routes."""
import pytest

from .conftest import ADMIN_TOKEN


class TestLogin:
    def test_get_login_page(self, client):
        r = client.get('/login')
        assert r.status_code == 200
        assert b'login' in r.data.lower() or b'token' in r.data.lower()

    def test_login_success_redirects_to_dashboard(self, client):
        r = client.post('/login', data={'token': ADMIN_TOKEN})
        assert r.status_code == 302
        assert '/' in r.headers['Location']

    def test_login_wrong_token_stays_on_login(self, client):
        r = client.post('/login', data={'token': 'wrong'}, follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid token' in r.data

    def test_login_empty_token_rejected(self, client):
        r = client.post('/login', data={'token': ''}, follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid token' in r.data

    def test_unauthenticated_redirect_to_login(self, client):
        for path in ('/', '/backups', '/mods', '/players', '/world', '/console'):
            r = client.get(path)
            assert r.status_code == 302, f'{path} should redirect unauthenticated'
            assert '/login' in r.headers['Location'], f'{path} should redirect to login'

    def test_logout_clears_session(self, app):
        c = app.test_client()
        # Authenticate
        c.post('/login', data={'token': ADMIN_TOKEN})
        # Logout
        r = c.get('/logout')
        assert r.status_code == 302
        # After logout, dashboard is protected again
        r = c.get('/')
        assert r.status_code == 302
        assert '/login' in r.headers['Location']
