import ipaddress
import urllib.parse

import requests

# Only allow REST calls to loopback or private-network addresses to prevent
# an attacker from using a crafted REST_URL to pivot to internal services.
_ALLOWED_REST_HOSTS = frozenset({'127.0.0.1', '::1', 'localhost'})


def _is_safe_rest_url(url: str) -> bool:
    """Return True if url points to localhost or a private IP."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ''
        if host in _ALLOWED_REST_HOSTS:
            return True
        addr = ipaddress.ip_address(host)
        return addr.is_loopback or addr.is_private
    except Exception:
        return False


def rest_call(endpoint, cfg, method='GET', data=None):
    """Call TShock REST API. Only used when server_type == tshock."""
    if not _is_safe_rest_url(cfg.REST_URL):
        return {'status': 'error', 'error': 'REST_URL must point to localhost or a private network address'}
    try:
        url = f"{cfg.REST_URL}{endpoint}"
        params = {'token': cfg.REST_TOKEN}
        if data:
            params.update(data)
        if method == 'GET':
            resp = requests.get(url, params=params, timeout=5)
        else:
            resp = requests.post(url, data=params, timeout=5)
        return resp.json() if resp.text else {'status': resp.status_code}
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'error': 'Server offline or REST API disabled'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}
