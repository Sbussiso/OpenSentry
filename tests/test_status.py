import os
import time
import threading
import requests
import pytest

# Simple smoke tests that the container/server exposes /status
# These are designed to run in GitHub Actions by hitting the exposed port

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
TOKEN = os.environ.get("OPENSENTRY_API_TOKEN", "")


def test_status_without_token_ok_when_no_token_configured():
    # If the app is configured with a token, skip this test.
    if TOKEN:
        pytest.skip("OPENSENTRY_API_TOKEN set; skipping unauthenticated /status test")
    # If token is not set in the app, /status should respond 200 without auth
    # In CI, the first job doesn't set a token, so this should pass.
    r = requests.get(f"{BASE}/status", timeout=5)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data and isinstance(data["id"], str)
    assert "name" in data and isinstance(data["name"], str)
    assert "version" in data and isinstance(data["version"], str)
    assert "routes" in data and isinstance(data["routes"], dict)
    # In snapshot mode, we only have snapshots route
    assert "snapshots" in data["routes"]
    assert "camera" in data and isinstance(data["camera"], dict)
    assert set(["running","has_frame"]).issubset(set(data["camera"].keys()))


def test_status_with_token_enforced_when_set():
    # This test expects the app to be started with a token in the environment.
    # If no token provided to the test process, skip.
    if not TOKEN:
        return
    # Should be unauthorized without header
    r = requests.get(f"{BASE}/status", timeout=5)
    assert r.status_code in (401, 403)
    # Wrong token should be unauthorized/forbidden
    r_bad = requests.get(f"{BASE}/status", headers={"Authorization": "Bearer wrong"}, timeout=5)
    assert r_bad.status_code in (401, 403)
    # With correct token should be 200
    r2 = requests.get(f"{BASE}/status", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=5)
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data.get("auth_mode") == "token"
