"""The safety net for 'deny by default': every endpoint except login and /health must refuse a request that has no valid login.

If someone adds an endpoint and forgets to protect it, this fails. Run it with:  pip install pytest && pytest
"""
from fastapi.testclient import TestClient

from main import app

PUBLIC = {("POST", "/auth/login"), ("GET", "/health")}  # the only endpoints that may be called without logging in


def endpoints(client):
    """Every (method, path) the API declares."""
    spec = client.get("/openapi.json").json()
    return [(method.upper(), path) for path, methods in spec["paths"].items() for method in methods if (method.upper(), path) not in PUBLIC]


def test_every_endpoint_refuses_a_request_with_no_login():
    with TestClient(app) as client:
        found = endpoints(client)
        assert len(found) > 10  # guards against the check silently looking at nothing
        open_ones = []
        for method, path in found:
            status = client.request(method, path, json={} if method == "POST" else None).status_code
            if status != 401:
                open_ones.append((method, path, status))
        assert not open_ones, f"these endpoints answered something other than 401 without a login: {open_ones}"


def test_every_endpoint_refuses_a_wrong_token():
    with TestClient(app) as client:
        headers = {"emp-code": "NX-4471", "session-token": "not-a-real-token"}
        wrong = [(m, p) for m, p in endpoints(client) if client.request(m, p, headers=headers, json={} if m == "POST" else None).status_code != 401]
        assert not wrong, f"a made-up token was not refused on: {wrong}"


def test_other_websites_are_given_no_permission_to_call_the_api():
    with TestClient(app) as client:
        reply = client.options("/get_templates", headers={"Origin": "https://some-other-site.example", "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in reply.headers
