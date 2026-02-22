import requests


def rest_call(endpoint, cfg, method='GET', data=None):
    """Call TShock REST API. Only used when server_type == tshock."""
    try:
        url = f"{cfg.REST_URL}{endpoint}"
        params = {'token': cfg.REST_TOKEN}
        if method == 'GET':
            if data:
                params.update(data)
            resp = requests.get(url, params=params, timeout=5)
        else:
            if data:
                params.update(data)
            resp = requests.post(url, data=params, timeout=5)
        return resp.json() if resp.text else {'status': resp.status_code}
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'error': 'Server offline or REST API disabled'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}
