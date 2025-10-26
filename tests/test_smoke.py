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


def test_video_feed_stream_headers_and_chunk():
    s = _login_session()
    r = s.get(f"{BASE}/video_feed", stream=True, timeout=10)
    assert r.status_code == 200
    ct = r.headers.get("Content-Type", "")
    assert ct.startswith("multipart/x-mixed-replace")
    assert r.headers.get("X-Accel-Buffering") == "no"
    # Custom headers present
    assert "Server" in r.headers
    # read one small chunk to verify stream emits data
    chunk = next(r.iter_content(chunk_size=1024))
    assert b"--frame" in chunk or b"Content-Type: image/jpeg" in chunk
    r.close()


def test_video_feed_motion_stream_headers_and_chunk():
    s = _login_session()
    r = s.get(f"{BASE}/video_feed_motion", stream=True, timeout=10)
    assert r.status_code == 200
    ct = r.headers.get("Content-Type", "")
    assert ct.startswith("multipart/x-mixed-replace")
    assert r.headers.get("X-Accel-Buffering") == "no"
    # Custom headers present
    assert "Server" in r.headers
    chunk = next(r.iter_content(chunk_size=1024))
    assert b"--frame" in chunk or b"Content-Type: image/jpeg" in chunk
    r.close()
