import os
import time
import requests
import pytest

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
USER = os.environ.get("OPENSENTRY_USER", "admin")
PASS = os.environ.get("OPENSENTRY_PASS", "admin")


def test_health_ok_and_headers():
    r = requests.get(f"{BASE}/health", timeout=5)
    assert r.status_code == 200
    # Observability headers should be present
    assert "Server" in r.headers
    assert "X-OpenSentry-Version" in r.headers
    assert "X-OpenSentry-Device" in r.headers


def test_settings_requires_login_redirect():
    r = requests.get(f"{BASE}/settings", timeout=5, allow_redirects=False)
    assert r.status_code in (301, 302)
    loc = r.headers.get("Location", "")
    assert "/login" in loc


def _login_session():
    s = requests.Session()
    # GET login (fetch cookies)
    s.get(f"{BASE}/login", timeout=5)
    # POST credentials
    resp = s.post(
        f"{BASE}/login",
        data={"username": USER, "password": PASS, "next": "/"},
        timeout=5,
        allow_redirects=True,
    )
    # After login, accessing index should be 200
    r2 = s.get(f"{BASE}/", timeout=5)
    assert r2.status_code == 200
    return s


def test_hls_quad_index_served():
    s = _login_session()
    r = s.get(f"{BASE}/hls/quad/index.m3u8", timeout=10)
    assert r.status_code == 200
    ct = r.headers.get("Content-Type", "")
    assert "mpegurl" in ct.lower()
    assert "Server" in r.headers
    assert len(r.text) > 0


def test_hls_raw_index_served():
    s = _login_session()
    r = s.get(f"{BASE}/hls/raw/index.m3u8", timeout=10)
    # Allow 404 if raw hasn't started yet; touching /hls/raw will start it then index should appear soon
    if r.status_code == 404:
        # Trigger start by requesting the directory index via /hls/raw/index.m3u8 again after a short wait
        time.sleep(1.0)
        r = s.get(f"{BASE}/hls/raw/index.m3u8", timeout=10)
    assert r.status_code == 200
    ct = r.headers.get("Content-Type", "")
    assert "mpegurl" in ct.lower()
    assert "Server" in r.headers
    assert len(r.text) > 0
