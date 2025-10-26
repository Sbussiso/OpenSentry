import threading
import time
import os
import logging
import atexit
import numpy as np
import uuid
import socket
import json
import io
from collections import deque
 
from flask import Flask, Response, request, redirect, url_for, send_file, abort, session, render_template_string, jsonify
from io import BytesIO
import cv2
from helpers.camera import CameraStream
from helpers.settings_page import render_settings_page
from helpers.index_page import render_index_page
from helpers.theme import get_css, header_html
from helpers.mdns import MdnsAdvertiser
from helpers.encoders import init_jpeg_encoder, encode_jpeg_bgr
from helpers.frame_hub import Broadcaster
from helpers.config import load_config as _load_config, save_config as _save_config

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PORT = int(os.environ.get('OPENSENTRY_PORT', '5000'))
APP_VERSION = os.environ.get('OPENSENTRY_VERSION', '0.1.0')
DEVICE_NAME = os.environ.get('OPENSENTRY_DEVICE_NAME', 'OpenSentry')
API_TOKEN = os.environ.get('OPENSENTRY_API_TOKEN', '').strip()
MDNS_DISABLE = os.environ.get('OPENSENTRY_MDNS_DISABLE', '0') in ('1', 'true', 'TRUE')

# mDNS state
_mdns_adv = None
_startup_logged = False

# Logging configuration
LOG_LEVEL = (os.environ.get('OPENSENTRY_LOG_LEVEL', 'INFO') or 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger('opensentry')
# Initialize fast JPEG encoder (TurboJPEG if available; falls back to OpenCV)
try:
    init_jpeg_encoder(logger)
except Exception:
    pass

# In-memory ring buffer for recent logs (download via /logs/download)
class _RingBufferHandler(logging.Handler):
    def __init__(self, max_bytes: int = 1_048_576, max_lines: int = 10_000):
        super().__init__()
        self.max_bytes = int(max_bytes)
        self.max_lines = int(max_lines)
        self._buf = deque()
        self._bytes = 0
        self._lock = threading.Lock()

    def emit(self, record):
        try:
            msg = self.format(record) + '\n'
        except Exception:
            try:
                msg = record.getMessage() + '\n'
            except Exception:
                msg = '\n'
        data = msg.encode('utf-8', 'replace')
        with self._lock:
            self._buf.append(data)
            self._bytes += len(data)
            while self._bytes > self.max_bytes or len(self._buf) > self.max_lines:
                old = self._buf.popleft()
                self._bytes -= len(old)

    def dump(self, n: int | None = None) -> bytes:
        with self._lock:
            if n is not None and n > 0 and n < len(self._buf):
                items = list(self._buf)[-n:]
            else:
                items = list(self._buf)
        return b''.join(items)

_logbuf_handler = _RingBufferHandler(
    max_bytes=int(os.environ.get('OPENSENTRY_LOG_BUFFER_BYTES', '1048576')),
    max_lines=int(os.environ.get('OPENSENTRY_LOG_BUFFER_LINES', '10000')),
)
_logbuf_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s'))
logging.getLogger().addHandler(_logbuf_handler)

# --- Simple session-based authentication ---
app.secret_key = os.environ.get('OPENSENTRY_SECRET', 'change-this-in-prod')
app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)

_LOGIN_USER = os.environ.get('OPENSENTRY_USER', 'admin')
_LOGIN_PASS = os.environ.get('OPENSENTRY_PASS', 'admin')

# --- OAuth2 authentication support ---
import base64
import hashlib
import hmac
import secrets
import urllib.parse

# Auth config defaults (loaded from config.json)
auth_config = {
    'auth_mode': 'local',  # 'local' or 'oauth2'
    'oauth2_base_url': '',
    'oauth2_client_id': '',
    'oauth2_client_secret': '',
    'oauth2_scope': 'openid profile email offline_access',
}

def _oauth2_enabled() -> bool:
    """Return True only if OAuth2 mode is selected AND minimally configured.
    This prevents CI or local runs from failing when OAuth2 isn't set up.
    """
    try:
        mode = str(auth_config.get('auth_mode', 'local')).lower()
        base = (auth_config.get('oauth2_base_url') or '').strip()
        cid = (auth_config.get('oauth2_client_id') or '').strip()
        return (mode == 'oauth2') and bool(base) and bool(cid)
    except Exception:
        return False

def _gen_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge for OAuth2 flow."""
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge

def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip('=')

def _b64urldecode(s: str) -> bytes:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def _make_state(extra: dict | None = None) -> str:
    payload: dict = {"t": int(time.time()), "n": secrets.token_urlsafe(16)}
    if extra:
        payload.update(extra)
    raw = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
    key = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
    sig = hmac.new(key, raw, hashlib.sha256).digest()
    return f"{_b64url(raw)}.{_b64url(sig)}"

def _verify_state(state: str, max_age_sec: int = 600) -> dict | None:
    try:
        raw_b64, sig_b64 = state.split('.', 1)
        raw = _b64urldecode(raw_b64)
        sig = _b64urldecode(sig_b64)
        key = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
        expected = hmac.new(key, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(raw.decode())
        t = int(data.get('t') or 0)
        if not t or (int(time.time()) - t) > max_age_sec:
            return None
        return data
    except Exception:
        return None

def _probe_oauth2(base_url: str) -> tuple[bool, dict | str]:
    """Validate OAuth2 base URL by fetching OIDC well-known metadata.
    Returns (ok, info) where info is metadata dict on success or error string on failure.
    """
    import requests

    def _fetch(url: str):
        try:
            r = requests.get(url, timeout=3)
            if r.status_code != 200:
                return False, f"status {r.status_code}"
            data = r.json()
            return True, data
        except Exception as e:
            return False, str(e)

    base = base_url.rstrip("/")
    # Try OIDC discovery first
    ok, info = _fetch(f"{base}/.well-known/openid-configuration")
    if not ok:
        # Fallback to RFC8414 location
        ok, info = _fetch(f"{base}/.well-known/oauth-authorization-server")
        if not ok:
            return False, info
    # Minimal validation
    if not isinstance(info, dict):
        return False, "invalid metadata"
    required = ("issuer", "authorization_endpoint", "token_endpoint")
    if not all(k in info and isinstance(info[k], str) and info[k] for k in required):
        return False, "missing required fields"
    return True, info

def _auth_allowed() -> bool:
    # Allow unauthenticated access to only the login and OAuth2 routes
    ep = request.endpoint or ''
    if ep in ('login', 'oauth2_login', 'oauth2_callback', 'oauth2_fallback', 'api_oauth2_test', 'static', 'health', 'favicon', 'status'):
        return True
    return bool(session.get('logged_in'))


@app.before_request
def _require_login():
    # Enforce login before accessing any route except /login and OAuth2 routes
    if _auth_allowed():
        return None
    # Check if OAuth2 mode is enabled and properly configured
    if _oauth2_enabled():
        # If user opted into temporary local-login fallback, route to local login
        if session.get('oauth2_fallback'):
            nxt = request.full_path if request.query_string else request.path
            return redirect(url_for('login', next=nxt, fallback='1'))
        # Preserve next URL and redirect to OAuth2 login
        session['next'] = request.full_path if request.query_string else request.path
        return redirect(url_for('oauth2_login'))
    # Otherwise redirect to local login
    nxt = request.full_path if request.query_string else request.path
    return redirect(url_for('login', next=nxt))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Allow a local login even if OAuth2 is configured; only redirect to OAuth2 when not posting valid creds
    allow_fallback = bool(request.args.get('fallback')) or bool(session.get('oauth2_fallback'))
    # If user explicitly requested fallback, enable it for this session
    if request.method == 'GET' and request.args.get('fallback'):
        session['oauth2_fallback'] = True

    err = ''
    nxt = request.args.get('next') or request.form.get('next') or url_for('index')
    if request.method == 'POST':
        u = (request.form.get('username') or '').strip()
        p = request.form.get('password') or ''
        if u == _LOGIN_USER and p == _LOGIN_PASS:
            session['logged_in'] = True
            session['user'] = u
            return redirect(nxt)
        else:
            err = 'Invalid credentials'

    # If not successfully logged in via local auth, and OAuth2 is enabled without fallback, redirect to OAuth2
    if not session.get('logged_in') and _oauth2_enabled() and not allow_fallback:
        return redirect(url_for('oauth2_login'))
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>OpenSentry Login</title>
      <style>
        body {{ font-family: system-ui, Arial, sans-serif; background:#0b0e14; color:#eaeef2; display:flex; align-items:center; justify-content:center; height:100vh; }}
        .card {{ background:#11161f; padding:24px 28px; border-radius:12px; width:320px; box-shadow:0 6px 30px rgba(0,0,0,0.35); }}
        h1 {{ margin:0 0 14px; font-size:20px; }}
        label {{ display:block; margin:10px 0 6px; font-size:13px; color:#aab4c0; }}
        input[type=text], input[type=password] {{ width:100%; padding:10px 12px; border-radius:8px; border:1px solid #2a3342; background:#0e131b; color:#eaeef2; }}
        .btn {{ width:100%; margin-top:14px; padding:10px 12px; border:0; border-radius:8px; background:#3b82f6; color:#fff; font-weight:600; cursor:pointer; }}
        .btn:hover {{ background:#2563eb; }}
        .err {{ color:#f87171; font-size:13px; min-height:18px; margin-top:8px; }}
        .hint {{ color:#93a3b5; font-size:12px; margin-top:10px; }}
      </style>
    </head>
    <body>
      <form class="card" method="post">
        <h1>Login</h1>
        <input type="hidden" name="next" value="{nxt}">
        <label>Username</label>
        <input name="username" type="text" autocomplete="username" required>
        <label>Password</label>
        <input name="password" type="password" autocomplete="current-password" required>
        <div class="err">{err}</div>
        <button class="btn" type="submit">Sign in</button>
        <div class="hint">Default creds admin/admin. Set OPENSENTRY_USER, OPENSENTRY_PASS, OPENSENTRY_SECRET for production.</div>
      </form>
    </body>
    </html>
    """
    return render_template_string(html)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------- OAuth2 login flow ----------
@app.route('/oauth2/fallback')
def oauth2_fallback():
    """Enable a one-time local-login fallback for this session and redirect to login."""
    session['oauth2_fallback'] = True
    dest = request.args.get('next') or session.get('next') or url_for('index')
    return redirect(url_for('login', next=dest, fallback='1'))

@app.route('/oauth2/login')
def oauth2_login():
    if not _oauth2_enabled():
        return redirect(url_for('login'))
    ok, info = _probe_oauth2(auth_config.get('oauth2_base_url') or '')
    if not ok:
        nxt = session.get('next') or request.args.get('next') or url_for('index')
        # Render error page with fallback options
        error_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>OAuth2 Unavailable - OpenSentry</title>
          <style>
            :root {{ color-scheme: dark; }}
            body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:0; background:#0b0e14; color:#eaeef2; }}
            header {{ padding:14px 18px; background:#11161f; border-bottom:1px solid #1c2431; }}
            h1 {{ margin:0; font-size:18px; }}
            main {{ padding:16px 0; }}
            .container {{ max-width:800px; margin:0 auto; padding:0 16px; }}
            .card {{ background:#11161f; border:1px solid #1c2431; border-radius:12px; padding:16px; box-shadow:0 6px 30px rgba(0,0,0,0.25); }}
            .muted {{ color:#93a3b5; }}
            code {{ background:#0e131b; border:1px solid #2a3342; padding:2px 6px; border-radius:6px; }}
            .actions {{ display:flex; gap:10px; margin-top:14px; flex-wrap:wrap; }}
            a.btn {{ padding:10px 14px; border-radius:8px; text-decoration:none; font-weight:600; cursor:pointer; }}
            a.btn.primary {{ background:#3b82f6; color:#fff; }}
            a.btn.primary:hover {{ background:#2563eb; }}
            a.btn.secondary {{ background:#374151; color:#eaeef2; }}
            a.btn.secondary:hover {{ background:#1f2937; }}
          </style>
        </head>
        <body>
          <header>
            <h1>OAuth2 Unavailable</h1>
          </header>
          <main>
            <div class="container">
              <div class="card">
                <p class="muted">The configured OAuth2 server appears to be unavailable.</p>
                <p>Base URL: <code>{auth_config.get('oauth2_base_url') or 'Not configured'}</code></p>
                <p class="muted">Detail: {info}</p>
                <div class="actions">
                  <a class="btn primary" href="/oauth2/login?next={urllib.parse.quote(nxt)}">Retry OAuth2 login</a>
                  <a class="btn secondary" href="/oauth2/fallback?next={urllib.parse.quote(nxt)}">Use local login for now</a>
                  <a class="btn secondary" href="/settings">Settings</a>
                </div>
              </div>
            </div>
          </main>
        </body>
        </html>
        """
        return (error_html, 503)
    meta = info
    client_id = (auth_config.get('oauth2_client_id') or '').strip()
    if not client_id:
        return ("Missing oauth2_client_id in settings", 400)
    scope = (auth_config.get('oauth2_scope') or 'openid').strip()
    # Make session permanent to survive OAuth redirects
    session.permanent = True
    # Generate PKCE values
    code_verifier, code_challenge = _gen_pkce()
    # Embed code_verifier in the signed state so we can retrieve it even if session is lost
    state = _make_state(extra={'v': code_verifier})
    session['oauth2_state'] = state
    session['code_verifier'] = code_verifier
    redirect_uri = urllib.parse.urljoin(request.host_url, 'oauth2/callback')
    auth_url = meta.get('authorization_endpoint')
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': scope,
        'state': state,
        'code_challenge_method': 'S256',
        'code_challenge': code_challenge,
    }
    logger.info(f"OAuth2 login: state={state[:16]}..., redirect_uri={redirect_uri}")
    return redirect(auth_url + '?' + urllib.parse.urlencode(params))

@app.route('/oauth2/callback')
def oauth2_callback():
    if auth_config.get('auth_mode') != 'oauth2':
        return redirect(url_for('login'))
    import requests
    state = request.args.get('state')
    code = request.args.get('code')
    expected = session.get('oauth2_state')
    code_verifier_in_session = session.get('code_verifier')

    # Debug logging
    cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
    cookie_present = bool(request.cookies.get(cookie_name))
    state_verified = _verify_state(state) if state else None
    logger.info(f"OAuth2 callback: got_state={(state or '')[:16]}..., expected={(expected or '')[:16]}..., cookie_present={cookie_present}, code_verifier_present={bool(code_verifier_in_session)}, state_verified={bool(state_verified)}")

    valid_state = (expected and state == expected) or (state and _verify_state(state) is not None)
    if not code or not state or not valid_state:
        logger.error(f"OAuth2 callback validation failed: code={bool(code)}, state={bool(state)}, valid_state={valid_state}")
        return ("Invalid OAuth2 callback", 400)
    ok, info = _probe_oauth2(auth_config.get('oauth2_base_url') or '')
    if not ok:
        nxt = session.get('next') or url_for('index')
        error_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <title>OAuth2 Server Unavailable</title>
          <style>
            body {{ font-family: system-ui, Arial, sans-serif; background:#0b0e14; color:#eaeef2; padding:20px; }}
            .card {{ background:#11161f; padding:24px; border-radius:12px; max-width:600px; margin:40px auto; }}
            h1 {{ color:#f87171; }}
            code {{ background:#0e131b; padding:2px 6px; border-radius:6px; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>OAuth2 Server Unavailable</h1>
            <p>Error: <code>{info}</code></p>
            <p><a href="/oauth2/fallback?next={urllib.parse.quote(nxt)}">Use Local Login</a></p>
          </div>
        </body>
        </html>
        """
        return (error_html, 503)
    # Retrieve code_verifier from session for PKCE, or extract from verified state
    code_verifier = session.get('code_verifier')
    if not code_verifier:
        # Session was lost; try to recover code_verifier from the signed state
        state_data = _verify_state(state)
        if state_data and 'v' in state_data:
            code_verifier = state_data['v']
            logger.info(f"OAuth2 callback: recovered code_verifier from state")
        else:
            return ("Missing PKCE verifier in session. Please try logging in again.", 400)

    meta = info
    token_url = meta.get('token_endpoint')
    redirect_uri = urllib.parse.urljoin(request.host_url, 'oauth2/callback')
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': auth_config.get('oauth2_client_id') or '',
        'code_verifier': code_verifier,
    }
    # If a client secret is configured (confidential client), send it via POST (client_secret_post)
    cs = (auth_config.get('oauth2_client_secret') or '').strip()
    if cs:
        data['client_secret'] = cs

    # Debug logging
    logger.info(f"Token exchange: url={token_url}, client_id={data.get('client_id')}, redirect_uri={redirect_uri}, code={code[:20]}..., verifier={code_verifier[:20]}..., has_secret={bool(cs)}")

    try:
        r = requests.post(token_url, data=data, timeout=5)
        if r.status_code != 200:
            logger.error(f"Token exchange failed: {r.status_code}, response={r.text[:200]}")
            logger.error(f"Request data sent: {data}")
            return (f"Token exchange failed: {r.status_code}", 502)
        tok = r.json()
    except Exception as e:
        logger.error(f"Token exchange exception: {e}")
        return (f"Token exchange error: {e}", 502)
    # Minimal session establishment; in a full impl we would validate id_token
    session.pop('oauth2_state', None)
    session.pop('code_verifier', None)
    session['logged_in'] = True
    session['user'] = 'oauth2'
    session['oauth2_tokens'] = {k: tok.get(k) for k in ('access_token','refresh_token','id_token','expires_in','token_type')}
    dest = session.pop('next', None) or url_for('index')
    return redirect(dest)

# Health and favicon endpoints
@app.route('/health')
def health():
    return ('ok', 200, {'Content-Type': 'text/plain; charset=utf-8'})

@app.route('/favicon.ico')
def favicon():
    # Intentionally empty to silence 404s from browsers
    return ('', 204)

# Secure status endpoint for Command Center discovery/monitoring
@app.route('/status')
def status():
    # Enforce bearer token if configured
    if API_TOKEN:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return ({'error': 'unauthorized'}, 401)
        token = auth[len('Bearer '):].strip()
        if token != API_TOKEN:
            return ({'error': 'forbidden'}, 403)
    # Build status
    has_frame = (camera_stream.get_frame() is not None)
    raw_ok = camera_stream.running and has_frame
    motion_ok = raw_ok
    data = {
        'id': DEVICE_ID,
        'name': DEVICE_NAME,
        'version': APP_VERSION,
        'port': APP_PORT,
        'caps': ['raw','motion'],
        'routes': {
            'raw': bool(raw_ok),
            'motion': bool(motion_ok),
        },
        'camera': {
            'running': bool(camera_stream.running),
            'has_frame': bool(has_frame),
        },
        'auth_mode': 'token' if API_TOKEN else 'session',
    }
    return (data, 200)

@app.route('/logs/download')
def logs_download():
    """Download recent server logs as a text file. Optional query param n=<lines>."""
    # Parse optional ?n= lines param
    try:
        n = int(request.args.get('n', '0'))
    except Exception:
        n = 0
    payload = _logbuf_handler.dump(n if n > 0 else None)
    if not payload:
        payload = b'No logs captured yet.\n'
    buf = io.BytesIO(payload)
    buf.seek(0)
    resp = send_file(buf, mimetype='text/plain; charset=utf-8', as_attachment=True, download_name='opensentry-logs.txt')
    # Prevent caching
    try:
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    except Exception:
        pass
    return resp

# Stream output tuning (env-tunable)
OUTPUT_MAX_WIDTH = int(os.environ.get('OPENSENTRY_OUTPUT_MAX_WIDTH', '960'))
JPEG_QUALITY = int(os.environ.get('OPENSENTRY_JPEG_QUALITY', '75'))
RAW_TARGET_FPS = int(os.environ.get('OPENSENTRY_RAW_FPS', '15'))

# Video/stream configurable defaults and live config
VIDEO_DEFAULTS = {
    'width': 0,
    'height': 0,
    'fps': 15,
    'mjpeg': True,
}
STREAM_DEFAULTS = {
    'max_width': OUTPUT_MAX_WIDTH,
    'jpeg_quality': JPEG_QUALITY,
    'raw_fps': RAW_TARGET_FPS,
}
video_config = dict(VIDEO_DEFAULTS)
stream_config = dict(STREAM_DEFAULTS)

def _apply_video_stream_settings():
    """Apply current video/stream settings to runtime (env + globals) and refresh camera."""
    global OUTPUT_MAX_WIDTH, JPEG_QUALITY, RAW_TARGET_FPS
    # Apply stream settings
    try:
        OUTPUT_MAX_WIDTH = int(stream_config.get('max_width', OUTPUT_MAX_WIDTH))
        JPEG_QUALITY = int(stream_config.get('jpeg_quality', JPEG_QUALITY))
        RAW_TARGET_FPS = int(stream_config.get('raw_fps', RAW_TARGET_FPS))
    except Exception:
        pass
    # Apply camera settings via env for helpers.camera
    try:
        w = int(video_config.get('width', 0) or 0)
        h = int(video_config.get('height', 0) or 0)
        f = int(video_config.get('fps', 0) or 0)
        m = bool(video_config.get('mjpeg', True))
        if w > 0:
            os.environ['OPENSENTRY_CAMERA_WIDTH'] = str(w)
        else:
            os.environ.pop('OPENSENTRY_CAMERA_WIDTH', None)
        if h > 0:
            os.environ['OPENSENTRY_CAMERA_HEIGHT'] = str(h)
        else:
            os.environ.pop('OPENSENTRY_CAMERA_HEIGHT', None)
        if f > 0:
            os.environ['OPENSENTRY_CAMERA_FPS'] = str(f)
        else:
            os.environ.pop('OPENSENTRY_CAMERA_FPS', None)
        os.environ['OPENSENTRY_CAMERA_MJPEG'] = '1' if m else '0'
        # Update camera sleep interval and force reopen to apply
        try:
            if f > 0:
                camera_stream._sleep = 1.0 / max(1, f)
        except Exception:
            pass
        try:
            if camera_stream.camera is not None:
                camera_stream.camera.release()
        except Exception:
            pass
        camera_stream.camera = None
    except Exception:
        pass

# Thread-safe settings lock
settings_lock = threading.Lock()

# Motion detection defaults and settings (thread-safe, in-memory)
MOTION_DEFAULTS = {
    'threshold': 25,           # [DEPRECATED] pixel diff threshold (kept for compatibility)
    'min_area': 500,           # minimum contour area (pixels)
    'kernel': 15,              # [DEPRECATED] dilation kernel (kept for compatibility)
    'iterations': 2,           # [DEPRECATED] dilation iterations (kept for compatibility)
    'pad': 10,                 # box padding (px)
    'mog2_var_threshold': 16,  # MOG2 variance threshold (8-30, lower = more sensitive)
    'mog2_history': 500,       # MOG2 learning history (frames, ~30 sec @ 15fps)
}
motion_detection_config = MOTION_DEFAULTS.copy()

# Automatic snapshot defaults and settings
SNAPSHOT_DEFAULTS = {
    'enabled': False,          # Enable automatic snapshots on motion
    'cooldown': 15,            # Minimum seconds between snapshots (5-60)
    'motion_threshold': 5000,  # Minimum total motion area (pixels) to trigger
    'directory': 'snapshots',  # Directory to save snapshots (relative to BASE_DIR)
}
snapshot_config = SNAPSHOT_DEFAULTS.copy()

# Persisted config path
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

# Load persisted config if present
_cfg = _load_config(CONFIG_PATH)
# Ensure a persistent short device_id
DEVICE_ID = None
if _cfg:
    try:
        with settings_lock:
            if 'motion_detection' in _cfg:
                motion_detection_config.update(_cfg['motion_detection'])
            # Load auth config if present
            if 'auth' in _cfg and isinstance(_cfg['auth'], dict):
                auth_config.update(_cfg['auth'])
            # Load video/stream config if present
            try:
                if 'video' in _cfg and isinstance(_cfg['video'], dict):
                    video_config.update(_cfg['video'])
                if 'stream' in _cfg and isinstance(_cfg['stream'], dict):
                    stream_config.update(_cfg['stream'])
            except Exception:
                pass
            # Load snapshot config if present
            if 'snapshots' in _cfg and isinstance(_cfg['snapshots'], dict):
                snapshot_config.update(_cfg['snapshots'])
            # read existing device_id if present
            DEVICE_ID = _cfg.get('device_id') if isinstance(_cfg, dict) else None
        # Apply loaded video/stream settings (updates env and camera)
        try:
            _apply_video_stream_settings()
        except Exception:
            pass
    except Exception:
        DEVICE_ID = None

if not DEVICE_ID:
    # Generate short UUID and persist
    DEVICE_ID = uuid.uuid4().hex[:12]
    try:
        with settings_lock:
            _save_config(CONFIG_PATH, motion_detection_config, device_id=DEVICE_ID)
    except Exception:
        pass

# Ensure snapshots directory exists
def _get_snapshots_dir() -> str:
    """Get the full path to the snapshots directory and ensure it exists."""
    with settings_lock:
        rel_path = snapshot_config.get('directory', 'snapshots')
    full_path = os.path.join(BASE_DIR, rel_path)
    os.makedirs(full_path, exist_ok=True)
    return full_path

# Global camera stream (class imported from helpers.camera)
camera_stream = CameraStream()

# Ensure camera is released on shutdown
def _on_shutdown():
    try:
        if camera_stream and camera_stream.running:
            camera_stream.stop()
    except Exception:
        pass
    # Stop mDNS advertiser if running
    try:
        global _mdns_adv
        if _mdns_adv is not None:
            _mdns_adv.stop()
            _mdns_adv = None
    except Exception:
        pass

atexit.register(_on_shutdown)

@app.before_request
def _ensure_camera_started():
    global _startup_logged
    if not camera_stream.running:
        camera_stream.start()
    # One-time startup log and mDNS init for Gunicorn/WSGI path (Flask>=3 removed before_first_request)
    if not _startup_logged:
        try:
            logger.info("Device ID: %s, Version: %s, mDNS: %s", str(DEVICE_ID), str(APP_VERSION), 'ENABLED' if not MDNS_DISABLE else 'DISABLED')
        except Exception:
            pass
        _startup_logged = True
    try:
        _start_mdns_advertiser()
    except Exception:
        pass
    # Start broadcasters/workers once
    try:
        _ensure_hubs_started()
    except Exception:
        pass

# mDNS advertiser lifecycle
def _start_mdns_advertiser():
    global _mdns_adv
    if MDNS_DISABLE:
        return
    if _mdns_adv is not None:
        return
    try:
        txt = {
            'id': DEVICE_ID,
            'name': DEVICE_NAME,
            'ver': APP_VERSION,
            'caps': 'raw,motion',
            'auth': 'token' if API_TOKEN else 'session',
            'api': '/status,/health',
            'path': '/',
            'proto': '1',
        }
        adv = MdnsAdvertiser(DEVICE_NAME, APP_PORT, txt)
        adv.start()
        _mdns_adv = adv
        logger.info('mDNS advertised _opensentry._tcp.local for %s on port %d', DEVICE_NAME, APP_PORT)
    except Exception as e:
        logger.warning('mDNS advertise failed: %s', e)


# ---------- Centralized streaming hubs and background workers ----------

# Raw stream broadcaster (single encode shared by all clients)
def _produce_raw_jpeg() -> bytes | None:
    frame = camera_stream.get_frame()
    if frame is None:
        # Optional placeholder to make streams testable without a camera
        if os.environ.get('OPENSENTRY_ALLOW_PLACEHOLDER', '0') in ('1', 'true', 'TRUE'):
            import numpy as _np
            f = _np.zeros((480, 640, 3), dtype=_np.uint8)
            cv2.putText(f, 'NO CAMERA', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            return encode_jpeg_bgr(f, JPEG_QUALITY)
        return None
    # Downscale for output if needed
    H, W = frame.shape[:2]
    if W > OUTPUT_MAX_WIDTH:
        scale = OUTPUT_MAX_WIDTH / float(W)
        frame = cv2.resize(frame, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA)
    return encode_jpeg_bgr(frame, JPEG_QUALITY)


raw_broadcaster = Broadcaster(
    name='raw',
    produce_fn=_produce_raw_jpeg,
    fps_getter=lambda: int(stream_config.get('raw_fps', RAW_TARGET_FPS)),
)


class _MotionWorker:
    def __init__(self):
        self._th = None
        self._running = False
        self._lock = threading.Lock()
        self._latest: bytes | None = None
        self._prev_small = None
        self._proc_scale = 0.5
        self._bg_subtractor = None  # MOG2 background subtractor
        self._mog2_params = None  # Track current MOG2 parameters (var_threshold, history)
        self._last_snapshot_time = 0  # Track last automatic snapshot time (epoch seconds)

    def start(self):
        if self._running:
            return
        self._running = True
        self._th = threading.Thread(target=self._run, name='MotionWorker', daemon=True)
        self._th.start()

    def stop(self):
        self._running = False

    def get_latest(self) -> bytes | None:
        with self._lock:
            return self._latest

    def _maybe_save_snapshot(self, frame, contours, min_area: int):
        """Save automatic snapshot if conditions are met."""
        import time

        # Check if automatic snapshots are enabled
        with settings_lock:
            enabled = snapshot_config.get('enabled', False)
            if not enabled:
                return

            cooldown = int(snapshot_config.get('cooldown', 15))
            motion_threshold = int(snapshot_config.get('motion_threshold', 5000))

        # Check cooldown period
        current_time = time.time()
        if current_time - self._last_snapshot_time < cooldown:
            return

        # Calculate total motion area
        total_motion_area = sum(cv2.contourArea(c) for c in contours if cv2.contourArea(c) >= min_area)

        # Check if motion exceeds threshold
        if total_motion_area < motion_threshold:
            return

        # Save snapshot
        try:
            from datetime import datetime
            snapshots_dir = _get_snapshots_dir()
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            filename = f"{timestamp}_motion.jpg"
            filepath = os.path.join(snapshots_dir, filename)

            cv2.imwrite(filepath, frame)
            self._last_snapshot_time = current_time
            logger.info(f"Automatic snapshot saved: {filename} (motion area: {total_motion_area:.0f}px)")
        except Exception as e:
            logger.error(f"Failed to save automatic snapshot: {e}")

    def _run(self):
        last_send = 0.0
        while self._running:
            frame = camera_stream.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            # FPS cap for processing to avoid CPU spikes
            now_ts = time.time()
            target_fps = max(1, int(stream_config.get('raw_fps', RAW_TARGET_FPS)))
            min_interval = 1.0 / float(target_fps)
            if (now_ts - last_send) < min_interval:
                time.sleep(max(0.0, min_interval - (now_ts - last_send)))
            last_send = time.time()

            # Downscale for motion processing
            H, W = frame.shape[:2]
            small = cv2.resize(frame, (int(W * self._proc_scale), int(H * self._proc_scale)), interpolation=cv2.INTER_AREA)

            # Load settings snapshot
            cfg = _get_motion_settings_snapshot()
            var_threshold = int(cfg.get('mog2_var_threshold', 16))
            history = int(cfg.get('mog2_history', 500))
            min_area = int(cfg.get('min_area', 500))
            pad = int(cfg.get('pad', 10))

            # Initialize or reinitialize MOG2 if parameters changed
            current_params = (var_threshold, history)
            if self._bg_subtractor is None or self._mog2_params != current_params:
                self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                    history=history,           # Learn from N frames of history
                    varThreshold=var_threshold, # Pixel variance threshold (sensitivity)
                    detectShadows=False         # Disable shadow detection for speed
                )
                self._mog2_params = current_params
                logger.info(f"Initialized MOG2 background subtractor (history={history}, varThreshold={var_threshold})")

            # Apply MOG2 background subtraction (replaces frame differencing)
            fg_mask = self._bg_subtractor.apply(small)

            # Optional: Light morphological filtering to reduce noise
            # (much lighter than the old dilation approach)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            motion_detected = False
            x_min = y_min = x_max = y_max = None
            for contour in contours:
                if cv2.contourArea(contour) < min_area:
                    continue
                (x, y, w, h) = cv2.boundingRect(contour)
                if x_min is None:
                    x_min, y_min, x_max, y_max = x, y, x + w, y + h
                    motion_detected = True
                else:
                    x_min = min(x_min, x)
                    y_min = min(y_min, y)
                    x_max = max(x_max, x + w)
                    y_max = max(y_max, y + h)

            draw_frame = frame
            if motion_detected:
                inv = 1.0 / self._proc_scale
                x1 = int(max(0, x_min - pad) * inv)
                y1 = int(max(0, y_min - pad) * inv)
                x2 = int(min(small.shape[1] - 1, x_max + pad) * inv)
                y2 = int(min(small.shape[0] - 1, y_max + pad) * inv)
                cv2.rectangle(draw_frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
            status = "MOTION DETECTED" if motion_detected else "No Motion"
            color = (0, 0, 255) if motion_detected else (0, 255, 0)
            cv2.putText(draw_frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)

            # Automatic snapshot on motion detection
            if motion_detected:
                self._maybe_save_snapshot(draw_frame, contours, min_area)

            # Downscale for output if needed and encode
            H2, W2 = draw_frame.shape[:2]
            if W2 > OUTPUT_MAX_WIDTH:
                scale_out = OUTPUT_MAX_WIDTH / float(W2)
                draw_frame = cv2.resize(draw_frame, (int(W2 * scale_out), int(H2 * scale_out)), interpolation=cv2.INTER_AREA)

            jpg = encode_jpeg_bgr(draw_frame, JPEG_QUALITY)
            with self._lock:
                self._latest = jpg


_motion_worker = _MotionWorker()

motion_broadcaster = Broadcaster(
    name='motion',
    produce_fn=lambda: _motion_worker.get_latest(),
    fps_getter=lambda: int(stream_config.get('raw_fps', RAW_TARGET_FPS)),
)


_hubs_started = False

def _ensure_hubs_started():
    global _hubs_started
    if _hubs_started:
        return
    raw_broadcaster.start()
    _motion_worker.start()
    motion_broadcaster.start()
    _hubs_started = True

@app.after_request
def _add_observability_headers(resp):
    try:
        resp.headers['Server'] = f"OpenSentry/{APP_VERSION}"
        resp.headers['X-OpenSentry-Version'] = str(APP_VERSION)
        resp.headers['X-OpenSentry-Device'] = str(DEVICE_ID or '')
    except Exception:
        pass
    return resp


def _find_available_port(start_port: int, attempts: int = 10) -> int:
    """Find a free TCP port starting at start_port, trying up to attempts times."""
    for i in range(max(1, attempts)):
        p = start_port + i
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Allow quick reuse so the probe doesn't hold the port
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', p))
            s.close()
            return p
        except OSError:
            try:
                s.close()
            except Exception:
                pass
            continue
    return start_port


def generate_frames():
    """Centralized raw stream shared across clients."""
    return raw_broadcaster.multipart_stream()


def _get_motion_settings_snapshot():
    with settings_lock:
        return {
            'threshold': int(motion_detection_config.get('threshold', 25)),
            'kernel': int(motion_detection_config.get('kernel', 15)),
            'iterations': int(motion_detection_config.get('iterations', 2)),
            'min_area': int(motion_detection_config.get('min_area', 500)),
            'pad': int(motion_detection_config.get('pad', 10)),
            'mog2_var_threshold': int(motion_detection_config.get('mog2_var_threshold', 16)),
            'mog2_history': int(motion_detection_config.get('mog2_history', 500)),
        }


def generate_frames_with_detection():
    """Centralized motion stream shared across clients (background processing)."""
    return motion_broadcaster.multipart_stream()

 

 

 
@app.route('/')
def index():
    """Root endpoint - renders the index page via helper."""
    return render_index_page()

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Settings page for motion detection configuration."""
    if request.method == 'POST':
        # If reset button pressed, reset motion settings and redirect
        action = request.form.get('action')
        if action == 'reset_motion':
            with settings_lock:
                motion_detection_config.clear()
                motion_detection_config.update(MOTION_DEFAULTS)
            try:
                _save_config(CONFIG_PATH, motion_detection_config)
            except Exception:
                pass
            return redirect(url_for('settings'))

        # Handle OAuth2 authentication settings
        if action == 'update_auth':
            logger.info(f"Received update_auth request")
            auth_mode_in = (request.form.get('auth_mode') or '').strip().lower()
            oauth2_base_url_in = (request.form.get('oauth2_base_url') or '').strip()
            oauth2_client_id_in = (request.form.get('oauth2_client_id') or '').strip()
            oauth2_client_secret_in = (request.form.get('oauth2_client_secret') or '').strip()
            oauth2_scope_in = (request.form.get('oauth2_scope') or 'openid profile email offline_access').strip()

            logger.info(f"Auth mode: {auth_mode_in}, Base URL: {oauth2_base_url_in}, Client ID: {oauth2_client_id_in}")

            if auth_mode_in not in ('local', 'oauth2'):
                # Invalid mode; ignore
                logger.warning(f"Invalid auth_mode: {auth_mode_in}")
                return redirect(url_for('settings'))

            # If selecting oauth2, validate base_url via well-known fetch
            if auth_mode_in == 'oauth2':
                ok, info = _probe_oauth2(oauth2_base_url_in)
                if not ok:
                    logger.error(f"OAuth2 validation failed: {info}")
                    # For now, just redirect back to settings. In production, you might want to show an error message.
                    return redirect(url_for('settings'))
                if not oauth2_client_id_in:
                    logger.error("OAuth2 client_id required but not provided")
                    return redirect(url_for('settings'))

            with settings_lock:
                auth_config['auth_mode'] = auth_mode_in
                if auth_mode_in == 'oauth2':
                    auth_config['oauth2_base_url'] = oauth2_base_url_in
                    auth_config['oauth2_client_id'] = oauth2_client_id_in
                    auth_config['oauth2_client_secret'] = oauth2_client_secret_in
                    auth_config['oauth2_scope'] = oauth2_scope_in or 'openid profile email offline_access'
                else:
                    auth_config['oauth2_base_url'] = ''
                    auth_config['oauth2_client_id'] = ''
                    auth_config['oauth2_client_secret'] = ''
                    auth_config['oauth2_scope'] = 'openid profile email offline_access'

                # Persist config to disk
                try:
                    logger.info(f"Saving auth config to disk: {auth_config}")
                    _save_config(CONFIG_PATH, motion_detection_config, auth_config=auth_config)
                    logger.info("Auth config saved successfully")
                except Exception as e:
                    logger.error(f"Failed to save auth config: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            return redirect(url_for('settings'))

        # Read motion detection sensitivity values with fallbacks
        def _to_int(val, default):
            try:
                return int(val)
            except Exception:
                return default

        ma_in = _to_int(request.form.get('md_min_area', ''), motion_detection_config['min_area'])
        pd_in = _to_int(request.form.get('md_pad', ''), motion_detection_config['pad'])
        mog2_var_in = _to_int(request.form.get('mog2_var_threshold', ''), motion_detection_config.get('mog2_var_threshold', 16))
        mog2_hist_in = _to_int(request.form.get('mog2_history', ''), motion_detection_config.get('mog2_history', 500))

        # Clamp to sane ranges
        ma_in = max(0, ma_in)
        pd_in = max(0, pd_in)
        mog2_var_in = max(8, min(30, mog2_var_in))
        mog2_hist_in = max(200, min(1000, mog2_hist_in))

        with settings_lock:
            # Motion sensitivity
            motion_detection_config['min_area'] = ma_in
            motion_detection_config['pad'] = pd_in
            motion_detection_config['mog2_var_threshold'] = mog2_var_in
            motion_detection_config['mog2_history'] = mog2_hist_in
            # Camera & Stream settings from form
            def _to_int2(val, default):
                try:
                    return int(val)
                except Exception:
                    return default
            cam_width_in = request.form.get('cam_width')
            cam_height_in = request.form.get('cam_height')
            cam_fps_in = request.form.get('cam_fps')
            cam_mjpeg_in = 'cam_mjpeg' in request.form
            stream_jpeg_q_in = request.form.get('stream_jpeg_quality')
            stream_max_w_in = request.form.get('stream_max_width')
            stream_raw_fps_in = request.form.get('stream_raw_fps')
            if cam_width_in is not None and cam_width_in != '':
                video_config['width'] = max(0, _to_int2(cam_width_in, video_config.get('width', 0)))
            if cam_height_in is not None and cam_height_in != '':
                video_config['height'] = max(0, _to_int2(cam_height_in, video_config.get('height', 0)))
            if cam_fps_in is not None and cam_fps_in != '':
                video_config['fps'] = max(1, _to_int2(cam_fps_in, video_config.get('fps', 15)))
            video_config['mjpeg'] = bool(cam_mjpeg_in)
            if stream_jpeg_q_in is not None and stream_jpeg_q_in != '':
                stream_config['jpeg_quality'] = max(30, min(95, _to_int2(stream_jpeg_q_in, stream_config.get('jpeg_quality', JPEG_QUALITY))))
            if stream_max_w_in is not None and stream_max_w_in != '':
                stream_config['max_width'] = max(320, _to_int2(stream_max_w_in, stream_config.get('max_width', OUTPUT_MAX_WIDTH)))
            if stream_raw_fps_in is not None and stream_raw_fps_in != '':
                stream_config['raw_fps'] = max(1, _to_int2(stream_raw_fps_in, stream_config.get('raw_fps', RAW_TARGET_FPS)))

            # Snapshot settings from form
            snapshot_enabled_in = 'snapshot_enabled' in request.form
            snapshot_cooldown_in = _to_int2(request.form.get('snapshot_cooldown', ''), snapshot_config.get('cooldown', 15))
            snapshot_threshold_in = _to_int2(request.form.get('snapshot_motion_threshold', ''), snapshot_config.get('motion_threshold', 5000))
            snapshot_dir_in = (request.form.get('snapshot_directory', '') or 'snapshots').strip()

            snapshot_config['enabled'] = snapshot_enabled_in
            snapshot_config['cooldown'] = max(5, min(60, snapshot_cooldown_in))
            snapshot_config['motion_threshold'] = max(1000, min(20000, snapshot_threshold_in))
            snapshot_config['directory'] = snapshot_dir_in

        # Apply live and persist config to disk after general update
        try:
            _apply_video_stream_settings()
        except Exception:
            pass
        try:
            _save_config(CONFIG_PATH, motion_detection_config, video_config=video_config, stream_config=stream_config, snapshot_config=snapshot_config)
        except Exception:
            pass
        return redirect(url_for('settings'))

    with settings_lock:
        m_min_area = motion_detection_config['min_area']
        m_pad = motion_detection_config['pad']
        mog2_var_threshold = motion_detection_config.get('mog2_var_threshold', 16)
        mog2_history = motion_detection_config.get('mog2_history', 500)
        # Snapshot config
        snapshot_enabled = snapshot_config.get('enabled', False)
        snapshot_cooldown = snapshot_config.get('cooldown', 15)
        snapshot_motion_threshold = snapshot_config.get('motion_threshold', 5000)
        snapshot_directory = snapshot_config.get('directory', 'snapshots')

    # Snapshot simple route health/status
    has_frame = (camera_stream.get_frame() is not None)
    raw_ok = camera_stream.running and has_frame
    motion_ok = raw_ok  # motion depends on camera frames

    page_html = render_settings_page(
        m_min_area=m_min_area,
        m_pad=m_pad,
        mog2_var_threshold=mog2_var_threshold,
        mog2_history=mog2_history,
        raw_ok=raw_ok,
        motion_ok=motion_ok,
        device_id=str(DEVICE_ID or ''),
        port=int(APP_PORT),
        mdns_enabled=(not MDNS_DISABLE),
        app_version=str(APP_VERSION),
        auth_mode=str(auth_config.get('auth_mode', 'local')),
        oauth2_base_url=str(auth_config.get('oauth2_base_url', '')),
        oauth2_client_id=str(auth_config.get('oauth2_client_id', '')),
        oauth2_client_secret=str(auth_config.get('oauth2_client_secret', '')),
        oauth2_scope=str(auth_config.get('oauth2_scope', 'openid profile email offline_access')),
        cam_width=int(video_config.get('width', 0)),
        cam_height=int(video_config.get('height', 0)),
        cam_fps=int(video_config.get('fps', 15)),
        cam_mjpeg=bool(video_config.get('mjpeg', True)),
        out_max_width=int(stream_config.get('max_width', OUTPUT_MAX_WIDTH)),
        jpeg_quality=int(stream_config.get('jpeg_quality', JPEG_QUALITY)),
        raw_fps=int(stream_config.get('raw_fps', RAW_TARGET_FPS)),
        snapshot_enabled=snapshot_enabled,
        snapshot_cooldown=snapshot_cooldown,
        snapshot_motion_threshold=snapshot_motion_threshold,
        snapshot_directory=snapshot_directory,
    )
    return page_html

@app.route('/api/oauth2/test')
def api_oauth2_test():
    """Test OAuth2 connection by fetching well-known metadata."""
    base = (request.args.get('base_url') or '').strip()
    if not base:
        return jsonify({"ok": False, "error": "base_url required"}), 400
    ok, info = _probe_oauth2(base)
    if ok:
        return jsonify({
            "ok": True,
            "issuer": info.get("issuer"),
            "authorization_endpoint": info.get("authorization_endpoint"),
            "token_endpoint": info.get("token_endpoint")
        })
    return jsonify({"ok": False, "error": info}), 502

@app.route('/api/snapshot')
def api_snapshot():
    """Capture a snapshot of the current motion detection frame."""
    frame_data = _motion_worker.get_latest()
    if frame_data is None:
        return jsonify({"error": "No frame available"}), 503

    # Return the JPEG frame directly
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    resp = Response(frame_data, mimetype='image/jpeg')
    resp.headers['Content-Disposition'] = f'attachment; filename="opensentry-snapshot-{timestamp}.jpg"'
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

@app.route('/video_feed')
def video_feed():
    """Video streaming route - raw feed with no processing"""
    resp = Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp

@app.route('/video_feed_motion')
def video_feed_motion():
    """Video streaming route - motion detection overlay (alias)"""
    resp = Response(generate_frames_with_detection(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp


def main():
    global APP_PORT
    logger.info("Starting OpenSentry camera server...")
    logger.info("Starting camera stream...")
    camera_stream.start()
    # Choose a port (default 5000). If busy, try the next few ports.
    try:
        preferred = int(os.environ.get('OPENSENTRY_PORT', str(APP_PORT or 5000)))
    except Exception:
        preferred = 5000
    chosen = _find_available_port(preferred, attempts=10)
    # Update global APP_PORT so /status and mDNS advertise correctly
    APP_PORT = chosen
    logger.info("Binding HTTP server on port %d (preferred %d)", chosen, preferred)
    logger.info("Device ID: %s, Version: %s, mDNS: %s", str(DEVICE_ID), str(APP_VERSION), 'ENABLED' if not MDNS_DISABLE else 'DISABLED')
    logger.info("Access the feed at http://0.0.0.0:%d/video_feed", chosen)
    # Start mDNS advertisement after selecting the port
    try:
        _start_mdns_advertiser()
    except Exception:
        pass
    app.run(host='0.0.0.0', port=chosen, debug=False, threaded=True)


if __name__ == "__main__":
    main()
