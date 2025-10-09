import cv2
import threading
import time
import os
import logging
import atexit
import numpy as np
import uuid
import socket
import json
try:
    import face_recognition  # type: ignore
except Exception:
    face_recognition = None  # type: ignore
from flask import Flask, Response, request, redirect, url_for, send_file, abort, session, render_template_string, jsonify
from helpers.camera import CameraStream
from helpers.yolo import get_yolo_model
from helpers.faces import get_face_cascade
from helpers.motion import create_motion_generator
from helpers.settings_page import render_settings_page
from helpers.index_page import render_index_page
from helpers.all_feeds_page import render_all_feeds_page
from helpers.theme import get_css, header_html
from helpers.mdns import MdnsAdvertiser
from helpers.face_dedup import (
    compute_phash as _compute_phash,
    hamming as _hamming,
    load_manifest as _load_manifest,
    append_manifest as _append_manifest,
    load_embed_manifest as _load_embed_manifest,
    append_embed_manifest as _append_embed_manifest,
    write_embed_manifest as _write_embed_manifest,
    load_known_manifest as _load_known_manifest,
    append_known_manifest as _append_known_manifest,
    compute_embedding as _compute_embedding,
    face_recognition_available,
)
from helpers.config import load_config as _load_config, save_config as _save_config

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PORT = int(os.environ.get('OPENSENTRY_PORT', '5000'))
APP_VERSION = os.environ.get('OPENSENTRY_VERSION', '0.1.0')
DEVICE_NAME = os.environ.get('OPENSENTRY_DEVICE_NAME', 'OpenSentry')
API_TOKEN = os.environ.get('OPENSENTRY_API_TOKEN', '').strip()
MDNS_DISABLE = os.environ.get('OPENSENTRY_MDNS_DISABLE', '0') in ('1', 'true', 'TRUE')
_mdns_adv = None
_startup_logged = False

# Logging configuration
LOG_LEVEL = (os.environ.get('OPENSENTRY_LOG_LEVEL', 'INFO') or 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger('opensentry')

# --- Simple session-based authentication ---
# Configure secret key (set OPENSENTRY_SECRET in environment for production)
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
    # Check if OAuth2 mode is enabled
    if auth_config.get('auth_mode') == 'oauth2':
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
    # If OAuth2 mode is active and no fallback requested, redirect to OAuth2 login
    allow_fallback = bool(request.args.get('fallback')) or bool(session.get('oauth2_fallback'))
    # If user explicitly requested fallback, enable it for this session
    if request.method == 'GET' and request.args.get('fallback'):
        session['oauth2_fallback'] = True
    if auth_config.get('auth_mode') == 'oauth2' and not allow_fallback:
        return redirect(url_for('oauth2_login'))

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
    if auth_config.get('auth_mode') != 'oauth2':
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
    objects_ok = True  # advertised capability; heavy check avoided here
    faces_ok = (get_face_cascade() is not None) and raw_ok
    data = {
        'id': DEVICE_ID,
        'name': DEVICE_NAME,
        'version': APP_VERSION,
        'port': APP_PORT,
        'caps': ['raw','motion','objects','faces'],
        'routes': {
            'raw': bool(raw_ok),
            'motion': bool(motion_ok),
            'objects': bool(objects_ok),
            'faces': bool(faces_ok),
        },
        'camera': {
            'running': bool(camera_stream.running),
            'has_frame': bool(has_frame),
        },
        'auth_mode': 'token' if API_TOKEN else 'session',
    }
    return (data, 200)

# Stream output tuning
OUTPUT_MAX_WIDTH = 960
JPEG_QUALITY = 75
RAW_TARGET_FPS = 15

# (YOLO is now handled in helpers.yolo; face_recognition is used via helpers.face_dedup)

# Object detection settings (thread-safe)
settings_lock = threading.Lock()
object_detection_config = {
    'select_all': True,   # when True, detect all classes
    'classes': set(),     # when select_all is False, detect only these class names
}

# Motion detection defaults and settings (thread-safe, in-memory)
MOTION_DEFAULTS = {
    'threshold': 25,   # pixel diff threshold; lower = more sensitive
    'min_area': 500,   # minimum contour area (pixels)
    'kernel': 15,      # dilation kernel (px)
    'iterations': 2,   # dilation iterations
    'pad': 10,         # box padding (px)
}
motion_detection_config = MOTION_DEFAULTS.copy()

# Face detection defaults and settings (in-memory)
FACE_DEFAULTS = {
    'archive_unknown': False,      # when True, archive snapshot of unknown faces
    'min_duration_sec': 15,        # how long a face must persist before archiving
    'archive_dir': os.path.join(BASE_DIR, 'archives', 'unknown_faces'),
    # Dedup config
    'dedup_enabled': True,
    'dedup_threshold': 10,         # Hamming distance threshold (0-64)
    'manifest_path': os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest.json'),
    'dedup_method': 'embedding',   # 'embedding' or 'phash'
    'embedding_threshold': 0.7,    # L2 distance threshold for embeddings
    'manifest_embed_path': os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json'),
    'cooldown_minutes': 0,
}
face_detection_config = FACE_DEFAULTS.copy()
# Face dedup utilities moved to helpers.face_dedup

# Known faces manifest path
KNOWN_EMBED_PATH = os.path.join(BASE_DIR, 'archives', 'known_faces', 'manifest_embeddings.json')

# Persisted config path
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

# Load persisted config if present
_cfg = _load_config(CONFIG_PATH)
# Ensure a persistent short device_id
DEVICE_ID = None
if _cfg:
    try:
        with settings_lock:
            if 'object_detection' in _cfg:
                object_detection_config.update(_cfg['object_detection'])
                # classes back to set
                if isinstance(object_detection_config.get('classes', set()), list):
                    object_detection_config['classes'] = set(object_detection_config['classes'])
            if 'motion_detection' in _cfg:
                motion_detection_config.update(_cfg['motion_detection'])
            if 'face_detection' in _cfg:
                face_detection_config.update(_cfg['face_detection'])
            # Load auth config if present
            if 'auth' in _cfg and isinstance(_cfg['auth'], dict):
                auth_config.update(_cfg['auth'])
            # read existing device_id if present
            DEVICE_ID = _cfg.get('device_id') if isinstance(_cfg, dict) else None
    except Exception:
        DEVICE_ID = None

if not DEVICE_ID:
    # Generate short UUID and persist
    DEVICE_ID = uuid.uuid4().hex[:12]
    try:
        with settings_lock:
            _save_config(CONFIG_PATH, object_detection_config, motion_detection_config, face_detection_config, device_id=DEVICE_ID)
    except Exception:
        pass

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
            'caps': 'raw,motion,objects,faces',
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
    """Generator function that yields raw frames in MJPEG format"""
    last_send = 0.0
    while True:
        frame = camera_stream.get_frame()
        if frame is None:
            # Optional placeholder to make streams testable without a camera
            if os.environ.get('OPENSENTRY_ALLOW_PLACEHOLDER', '0') in ('1', 'true', 'TRUE'):
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, 'NO CAMERA', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            else:
                time.sleep(0.1)
                continue

        # FPS limit
        now_ts = time.time()
        min_interval = 1.0 / max(1, RAW_TARGET_FPS)
        dt = now_ts - last_send
        if dt < min_interval:
            time.sleep(max(0.0, min_interval - dt))
        last_send = time.time()

        # Downscale for output if needed
        H, W = frame.shape[:2]
        if W > OUTPUT_MAX_WIDTH:
            scale = OUTPUT_MAX_WIDTH / float(W)
            frame = cv2.resize(frame, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA)

        # Encode frame as JPEG (lower quality to reduce CPU)
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)])
        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        # Yield frame in multipart format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n'
               b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' + frame_bytes + b'\r\n')


def generate_frames_with_objects():
    """Generator function that yields frames with YOLOv8n object detection overlays."""
    model = get_yolo_model()
    while True:
        frame = camera_stream.get_frame()
        if frame is None:
            time.sleep(0.1)
            continue

        # Snapshot settings to avoid holding the lock during inference
        with settings_lock:
            select_all = object_detection_config['select_all']
            allowed = set(object_detection_config['classes'])

        if model is None:
            # Informative overlay if ultralytics isn't installed or model failed
            msg = 'YOLOv8n unavailable. Install: uv add ultralytics'
            cv2.putText(frame, msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            try:
                results = model(frame, verbose=False)[0]
                names = getattr(results, 'names', {}) or getattr(model, 'names', {}) or {}
                if hasattr(results, 'boxes') and results.boxes is not None:
                    for b in results.boxes:
                        # xyxy tensor -> ints
                        xyxy = b.xyxy[0].cpu().numpy().tolist()
                        x1, y1, x2, y2 = [int(v) for v in xyxy]
                        conf = float(b.conf[0]) if getattr(b, 'conf', None) is not None else 0.0
                        cls_id = int(b.cls[0]) if getattr(b, 'cls', None) is not None else -1
                        label = names.get(cls_id, str(cls_id if cls_id >= 0 else 'obj'))
                        if not select_all and label not in allowed:
                            continue
                        color = (0, 255, 255)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        text = f"{label} {conf:.2f}"
                        cv2.putText(frame, text, (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            except Exception as e:
                cv2.putText(frame, f'YOLO error: {e}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Encode and yield
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n'
               b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' + frame_bytes + b'\r\n')


def generate_frames_with_faces():
    """Generator function that yields frames with face detection (Haar cascade)."""
    cascade = get_face_cascade()
    # Simple track state for persisting detections over time
    tracks = {}  # id -> {bbox:(x,y,w,h), start:float, last:float, archived:bool}
    next_id = 1

    def _iou(b1, b2):
        x1, y1, w1, h1 = b1
        x2, y2, w2, h2 = b2
        ax1, ay1, ax2, ay2 = x1, y1, x1 + w1, y1 + h1
        bx1, by1, bx2, by2 = x2, y2, x2 + w2, y2 + h2
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        iw = max(0, inter_x2 - inter_x1)
        ih = max(0, inter_y2 - inter_y1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        area_a = w1 * h1
        area_b = w2 * h2
        union = area_a + area_b - inter
        if union <= 0:
            return 0.0
        return inter / float(union)

    def _make_uid(ts_val: float) -> str:
        # Short, readable UID derived from timestamp ms; sufficient for unknown users
        ms = int((ts_val - int(ts_val)) * 1000)
        return f"U{int(ts_val)%100000:05d}{ms:03d}"

    while True:
        frame = camera_stream.get_frame()
        if frame is None:
            time.sleep(0.1)
            continue

        # Prefer face_recognition detection (HOG) when available; fallback to Haar cascade
        H, W = frame.shape[:2]
        valid = []
        used_detector = 'haar'
        if face_recognition_available and face_recognition is not None:
            try:
                target_w = 800
                scale = 1.0
                if W > target_w:
                    scale = target_w / float(W)
                    small = cv2.resize(frame, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_LINEAR)
                else:
                    small = frame
                small_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                boxes = face_recognition.face_locations(small_rgb, model='hog')  # (top, right, bottom, left)
                # Landmark-based validation: require eyes and nose to reduce false positives
                lmarks = []
                try:
                    lmarks = face_recognition.face_landmarks(small_rgb, boxes, model='small')
                except Exception:
                    lmarks = []
                inv = 1.0 / scale
                for i, (top, right, bottom, left) in enumerate(boxes):
                    lm = lmarks[i] if i < len(lmarks) else {}
                    # Relax gating: accept if eyes OR nose when landmarks are present; if no landmarks, allow box
                    landmarks_ok = True
                    if isinstance(lm, dict) and lm:
                        has_eyes = ('left_eye' in lm and 'right_eye' in lm and lm['left_eye'] and lm['right_eye'])
                        has_nose = ('nose_bridge' in lm and lm['nose_bridge'])
                        if not (has_eyes or has_nose):
                            landmarks_ok = False
                    if not landmarks_ok:
                        continue
                    x = int(left * inv)
                    y = int(top * inv)
                    w = int((right - left) * inv)
                    h = int((bottom - top) * inv)
                    # Aspect and min area filters
                    ar = w / float(h) if h > 0 else 0
                    area = w * h
                    if h <= 0 or w <= 0:
                        continue
                    if ar < 0.70 or ar > 1.40:
                        continue
                    if area < 0.008 * (W * H):  # at least 0.8% of the frame area
                        continue
                    x = max(0, min(W - 1, x))
                    y = max(0, min(H - 1, y))
                    w = max(1, min(W - x, w))
                    h = max(1, min(H - y, h))
                    valid.append((x, y, w, h))
                if valid:
                    used_detector = 'fr'
            except Exception:
                valid = []

        if not valid:
            if cascade is None:
                cv2.putText(frame, 'Face detector unavailable', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)
                # Slightly relaxed detector params and dynamic minimum size
                min_w = max(30, int(W * 0.09))
                min_h = max(30, int(H * 0.09))
                faces = cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.22,
                    minNeighbors=8,
                    minSize=(min_w, min_h)
                )
                # Filter by plausible face aspect ratio and minimum area
                min_area_ratio = 0.012  # 1.2% of frame area
                frame_area = float(W * H)
                for (x, y, w, h) in faces:
                    ar = w / float(h) if h > 0 else 0
                    area = w * h
                    if h <= 0 or w <= 0:
                        continue
                    if ar < 0.70 or ar > 1.40:
                        continue
                    if area < (min_area_ratio * frame_area):
                        continue
                    valid.append((x, y, w, h))
        # Snapshot face archiving settings
        with settings_lock:
            archive_enabled = bool(face_detection_config.get('archive_unknown', False))
            min_dur = float(face_detection_config.get('min_duration_sec', 10))
            archive_dir = str(face_detection_config.get('archive_dir', 'archives/unknown_faces'))
            embed_th_view = float(face_detection_config.get('embedding_threshold', 0.6))

        now = time.time()
        # Match detections to existing tracks by IoU
        used_tracks = set()
        for (x, y, w, h) in valid:
            best_id = None
            best_iou = 0.0
            for tid, t in tracks.items():
                if tid in used_tracks:
                    continue
                i = _iou((x, y, w, h), t['bbox'])
                if i > best_iou:
                    best_iou = i
                    best_id = tid
            if best_id is not None and best_iou >= 0.2:
                t = tracks[best_id]
                t['bbox'] = (x, y, w, h)
                t['last'] = now
                used_tracks.add(best_id)
            else:
                tid = next_id
                next_id += 1
                tracks[tid] = {'bbox': (x, y, w, h), 'start': now, 'last': now, 'archived': False, 'uid': None}
                used_tracks.add(tid)

        # Prune stale tracks
        stale_cutoff = now - 3.0
        for tid in list(tracks.keys()):
            if tracks[tid]['last'] < stale_cutoff:
                del tracks[tid]

        # Pre-pass: identify known faces so recognized tracks are not archived
        if face_recognition_available:
            try:
                k_entries = _load_known_manifest(KNOWN_EMBED_PATH)
            except Exception:
                k_entries = []
            if k_entries:
                for tid, t in tracks.items():
                    if t.get('name'):
                        continue
                    x, y, w, h = t['bbox']
                    x1 = max(0, x)
                    y1 = max(0, y)
                    x2 = min(W, x + w)
                    y2 = min(H, y + h)
                    if (x2 - x1) <= 1 or (y2 - y1) <= 1:
                        continue
                    # small padding for more stable embeddings
                    pad = int(max(w, h) * 0.1)
                    xx1 = max(0, x1 - pad)
                    yy1 = max(0, y1 - pad)
                    xx2 = min(W, x2 + pad)
                    yy2 = min(H, y2 + pad)
                    crop = frame[yy1:yy2, xx1:xx2]
                    emb_vec = _compute_embedding(crop)
                    if emb_vec is None:
                        continue
                    best_name = None
                    best_dist = 1e9
                    for e in k_entries:
                        try:
                            evec = np.asarray(e.get('embedding', []), dtype=np.float32)
                            if evec.size != emb_vec.size:
                                continue
                            dist = float(np.linalg.norm(emb_vec - evec))
                            if dist < best_dist:
                                best_dist = dist
                                best_name = e.get('name')
                        except Exception:
                            continue
                    if best_name is not None and best_dist <= embed_th_view:
                        t['name'] = best_name

        # Archive faces that persisted long enough
        if archive_enabled:
            os.makedirs(archive_dir, exist_ok=True)
            for tid, t in tracks.items():
                if t['archived']:
                    continue
                # Skip archiving if already recognized as known
                if t.get('name'):
                    continue
                if (now - t['start']) >= min_dur:
                    x, y, w, h = t['bbox']
                    x1 = max(0, x)
                    y1 = max(0, y)
                    x2 = min(W, x + w)
                    y2 = min(H, y + h)
                    if (x2 - x1) > 0 and (y2 - y1) > 0:
                        crop = frame[y1:y2, x1:x2]

                        # Dedup check: prefer embeddings if available and selected; fallback to pHash
                        with settings_lock:
                            dedup_enabled = bool(face_detection_config.get('dedup_enabled', True))
                            method = str(face_detection_config.get('dedup_method', 'embedding'))
                            embed_th = float(face_detection_config.get('embedding_threshold', 0.6))
                            dd_th = int(face_detection_config.get('dedup_threshold', 10))
                            manifest_path = str(face_detection_config.get('manifest_path', os.path.join(archive_dir, 'manifest.json')))
                            manifest_embed_path = str(face_detection_config.get('manifest_embed_path', os.path.join(archive_dir, 'manifest_embeddings.json')))
                            cooldown_min = int(face_detection_config.get('cooldown_minutes', 60))
                        is_dup = False
                        used_method = None
                        skip_save = False
                        emb_vec = None
                        matched_uid = None
                        matched_name = None

                        if dedup_enabled and method == 'embedding':
                            used_method = 'embedding'
                            if not face_recognition_available:
                                # Embedding pipeline not available; skip saves for embedding method
                                skip_save = True
                            else:
                                emb_vec = _compute_embedding(crop)
                                if emb_vec is not None:
                                    # Known-first matching
                                    try:
                                        k_entries = _load_known_manifest(KNOWN_EMBED_PATH)
                                    except Exception:
                                        k_entries = []
                                    best_name = None
                                    best_dist = 1e9
                                    for e in k_entries:
                                        try:
                                            evec = np.asarray(e.get('embedding', []), dtype=np.float32)
                                            if evec.size != emb_vec.size:
                                                continue
                                            dist = float(np.linalg.norm(emb_vec - evec))
                                            if dist < best_dist:
                                                best_dist = dist
                                                best_name = e.get('name')
                                        except Exception:
                                            continue
                                    if best_name is not None and best_dist <= embed_th:
                                        is_dup = True
                                        matched_name = best_name
                                    # Unknown-manifest matching
                                    entries = _load_embed_manifest(manifest_embed_path)
                                    cooldown_sec = max(0, cooldown_min) * 60
                                    # Use a slightly more lenient threshold for unknown dedup to avoid duplicate UIDs for the same person
                                    th_unknown = min(max(embed_th, 0.0) + 0.12, 1.0)
                                    best_uid = None
                                    best_uid_dist = 1e9
                                    for e in entries:
                                        try:
                                            evec = np.asarray(e.get('embedding', []), dtype=np.float32)
                                            if evec.size != emb_vec.size:
                                                continue
                                            dist = float(np.linalg.norm(emb_vec - evec))
                                            recent = (now - float(e.get('ts', 0))) <= cooldown_sec if cooldown_sec > 0 else True
                                            if recent and dist < best_uid_dist:
                                                best_uid_dist = dist
                                                best_uid = e.get('uid') or (f"U{int(float(e.get('ts', 0)))%100000:05d}")
                                        except Exception:
                                            continue
                                    if matched_name is None and best_uid is not None and best_uid_dist <= th_unknown:
                                        is_dup = True
                                        matched_uid = best_uid
                                else:
                                    # Embedding could not be computed; skip saving to avoid non-embedding fallback
                                    skip_save = True

                        if dedup_enabled and not is_dup and method == 'phash':
                            p = _compute_phash(crop)
                            entries = _load_manifest(manifest_path)
                            cooldown_sec = max(0, cooldown_min) * 60
                            for e in entries:
                                try:
                                    dist = _hamming(int(e.get('hash', 0)), p)
                                    recent = (now - float(e.get('ts', 0))) <= cooldown_sec if cooldown_sec > 0 else True
                                    if dist <= dd_th and recent:
                                        is_dup = True
                                        break
                                except Exception:
                                    continue
                            used_method = 'phash'

                        if is_dup:
                            # Assign matched UID to track for live overlay
                            # Determine which track this crop matched: pick the track whose bbox equals current crop
                            for tid2, t2 in tracks.items():
                                if t2['bbox'] == (x, y, w, h):
                                    if matched_name is not None:
                                        t2['name'] = matched_name
                                    elif matched_uid is not None:
                                        t2['uid'] = matched_uid
                                    break
                            continue
                        if skip_save:
                            continue

                        # Save snapshot and append manifest
                        ts = time.strftime('%Y%m%d_%H%M%S')
                        ms = int((now - int(now)) * 1000)
                        fname = f"unknown_{ts}_{ms}_{x1}_{y1}_{x2-x1}_{y2-y1}.jpg"
                        out_path = os.path.join(archive_dir, fname)
                        saved_ok = False
                        if not cv2.imwrite(out_path, crop):
                            # Failed to write image; abort archiving
                            continue
                        try:
                            if method == 'embedding':
                                if not face_recognition_available:
                                    raise Exception('Embedding not available')
                                if emb_vec is None:
                                    emb_vec = _compute_embedding(crop)
                                if emb_vec is None:
                                    raise Exception('Embedding compute failed')
                                # Assign/generate uid and persist with embedding
                                uid = _make_uid(now)
                                _append_embed_manifest(manifest_embed_path, {"uid": uid, "embedding": emb_vec.tolist(), "ts": float(now), "path": out_path})
                                # Attach uid to the matched track for overlay
                                for tid2, t2 in tracks.items():
                                    if t2['bbox'] == (x, y, w, h):
                                        t2['uid'] = uid
                                        break
                            else:
                                p = _compute_phash(crop)
                                _append_manifest(manifest_path, {"hash": int(p), "ts": float(now), "path": out_path})
                            saved_ok = True
                        except Exception:
                            saved_ok = False
                        if saved_ok:
                            logger.info(f"Archived face snapshot: {out_path}")
                            t['archived'] = True

        # Live known-face identification (per frame): match tracks to known manifest
        if face_recognition_available:
            try:
                k_entries = _load_known_manifest(KNOWN_EMBED_PATH)
            except Exception:
                k_entries = []
            if k_entries:
                for tid, t in tracks.items():
                    if t.get('name'):
                        continue
                    x, y, w, h = t['bbox']
                    x1 = max(0, x)
                    y1 = max(0, y)
                    x2 = min(W, x + w)
                    y2 = min(H, y + h)
                    if (x2 - x1) <= 1 or (y2 - y1) <= 1:
                        continue
                    crop = frame[y1:y2, x1:x2]
                    emb_vec = _compute_embedding(crop)
                    if emb_vec is None:
                        continue
                    best_name = None
                    best_dist = 1e9
                    for e in k_entries:
                        try:
                            evec = np.asarray(e.get('embedding', []), dtype=np.float32)
                            if evec.size != emb_vec.size:
                                continue
                            dist = float(np.linalg.norm(emb_vec - evec))
                            if dist < best_dist:
                                best_dist = dist
                                best_name = e.get('name')
                        except Exception:
                            continue
                    if best_name is not None and best_dist <= embed_th_view:
                        t['name'] = best_name

        color = (0, 200, 0) if used_detector == 'fr' else (255, 200, 0)
        # Draw using tracked boxes so we can label with UID or track id
        for tid, t in tracks.items():
            (x, y, w, h) = t['bbox']
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            name = t.get('name')
            if name:
                label_text = str(name)
            else:
                uid = t.get('uid')
                label_text = uid if uid else "Unknown"
            cv2.putText(frame, label_text, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        cv2.putText(frame, f'Faces: {len(valid)}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
        # Overlay archiving status
        arch_text = 'Archiving: ON' if archive_enabled else 'Archiving: OFF'
        arch_color = (0, 200, 0) if archive_enabled else (180, 180, 180)
        cv2.putText(frame, arch_text, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, arch_color, 2)

        # Encode and yield
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n'
               b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' + frame_bytes + b'\r\n')


def _get_motion_settings_snapshot():
    with settings_lock:
        return {
            'threshold': int(motion_detection_config.get('threshold', 25)),
            'kernel': int(motion_detection_config.get('kernel', 15)),
            'iterations': int(motion_detection_config.get('iterations', 2)),
            'min_area': int(motion_detection_config.get('min_area', 500)),
            'pad': int(motion_detection_config.get('pad', 10)),
        }


def generate_frames_with_detection():
    """Generator function that yields frames with motion detection overlay (via helpers.motion)."""
    gen = create_motion_generator(camera_stream, _get_motion_settings_snapshot)
    return gen()

@app.route('/archives/image')
def archives_image():
    path = request.args.get('path', '')
    if not path:
        abort(400)
    ap = os.path.abspath(path)
    archives_root = os.path.join(BASE_DIR, 'archives')
    if not ap.startswith(archives_root):
        abort(403)
    try:
        return send_file(ap)
    except Exception:
        abort(404)

@app.route('/archives/unknown_faces', methods=['GET', 'POST'])
def archives_unknown_faces():
    with settings_lock:
        unknown_manifest_path = str(face_detection_config.get('manifest_embed_path', os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json')))
    if request.method == 'POST':
        action = request.form.get('action', '')
        uid = request.form.get('uid', '').strip()
        if action == 'delete' and uid:
            entries = _load_embed_manifest(unknown_manifest_path)
            new_entries = []
            img_path = None
            for e in entries:
                if str(e.get('uid', '')) == uid:
                    img_path = e.get('path')
                    continue
                new_entries.append(e)
            try:
                _write_embed_manifest(unknown_manifest_path, new_entries)
            except Exception:
                pass
            if img_path:
                try:
                    os.remove(img_path)
                except Exception:
                    pass
            return redirect(url_for('archives_unknown_faces'))
        if action == 'promote' and uid:
            name = request.form.get('name', '').strip()
            if name:
                entries = _load_embed_manifest(unknown_manifest_path)
                pick = None
                for e in entries:
                    if str(e.get('uid', '')) == uid:
                        pick = e
                        break
                if pick is not None:
                    try:
                        _append_known_manifest(KNOWN_EMBED_PATH, {"name": name, "embedding": pick.get('embedding', []), "ts": pick.get('ts', 0), "path": pick.get('path', '')})
                    except Exception:
                        pass
                    # remove from unknown
                    new_entries = [e for e in entries if str(e.get('uid', '')) != uid]
                    try:
                        _write_embed_manifest(unknown_manifest_path, new_entries)
                    except Exception:
                        pass
            return redirect(url_for('archives_unknown_faces'))
    # GET: render page
    entries = _load_embed_manifest(unknown_manifest_path)
    # Simple inline HTML to list entries
    rows = []
    for e in entries:
        uid = str(e.get('uid', ''))
        ts = float(e.get('ts', 0.0))
        path = e.get('path', '')
        img_url = url_for('archives_image') + f"?path={path}"
        row = f"""
        <div class='card'>
          <div class='img'><img src='{img_url}' alt='{uid}'/></div>
          <div class='meta'><div><strong>{uid}</strong></div><div>{ts}</div></div>
          <form method='post' class='actions'>
            <input type='hidden' name='uid' value='{uid}'>
            <input type='text' name='name' placeholder='Name' />
            <button type='submit' name='action' value='promote'>Promote to Known</button>
            <button type='submit' name='action' value='delete' onclick="return confirm('Delete this snapshot and entry?');">Delete</button>
          </form>
        </div>
        """
        rows.append(row)
    css = get_css() + """
      .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap:12px; padding:10px; }
      .card { border:1px solid var(--border); border-radius:10px; overflow:hidden; display:flex; flex-direction:column; background:#0e131b; }
      .img img { width:100%; display:block; }
      .meta { padding:8px; display:flex; justify-content:space-between; align-items:center; color:var(--muted); }
      .actions { display:flex; gap:8px; padding:8px; align-items:center; border-top:1px solid var(--border); flex-wrap: wrap; }
      .actions input[type=text] { flex: 1; min-width:0; padding:8px 10px; background:#0e131b; color:var(--text); border:1px solid var(--border); border-radius:8px; }
      .actions button { padding:8px 12px; background: var(--accent); color:#fff; border:0; border-radius:8px; font-weight:600; cursor:pointer; }
    """
    hdr = header_html('Unknown Faces')

    html = f"""
    <!DOCTYPE html>
    <html lang='en'>
    <head>
      <meta charset='utf-8'>
      <meta name='viewport' content='width=device-width, initial-scale=1'>
      <title>Unknown Faces</title>
      <style>{css}</style>
    </head>
    <body>
      {hdr}
      <div class='grid'>
        {''.join(rows)}
      </div>
    </body>
    </html>
    """
    return html

 
@app.route('/')
def index():
    """Root endpoint - renders the index page via helper."""
    return render_index_page()

@app.route('/all_feeds')
def all_feeds():
    return render_all_feeds_page()

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Simple settings page to select YOLO classes (or All)."""
    # Resolve available class names without running inference if possible
    names = []
    model = get_yolo_model()
    try:
        if model is not None:
            raw_names = getattr(model, 'names', None)
            if isinstance(raw_names, dict):
                names = [raw_names[i] for i in sorted(raw_names.keys())]
            elif isinstance(raw_names, (list, tuple)):
                names = list(raw_names)
    except Exception:
        names = []

    if request.method == 'POST':
        # If reset button pressed, reset motion settings and redirect
        action = request.form.get('action')
        if action == 'reset_motion':
            with settings_lock:
                motion_detection_config.clear()
                motion_detection_config.update(MOTION_DEFAULTS)
            try:
                _save_config(CONFIG_PATH, object_detection_config, motion_detection_config, face_detection_config)
            except Exception:
                pass
            return redirect(url_for('settings'))
        if action == 'reset_face_manifest':
            # Clear the unknown face manifests (hash and embeddings)
            with settings_lock:
                mp = str(face_detection_config.get('manifest_path', os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest.json')))
                mp_e = str(face_detection_config.get('manifest_embed_path', os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json')))
            try:
                os.makedirs(os.path.dirname(mp), exist_ok=True)
                with open(mp, 'w', encoding='utf-8') as f:
                    f.write('[]')
            except Exception:
                pass
            try:
                os.makedirs(os.path.dirname(mp_e), exist_ok=True)
                with open(mp_e, 'w', encoding='utf-8') as f:
                    f.write('[]')
            except Exception:
                pass
            return redirect(url_for('settings'))

        # Manage unknowns directly from Settings: promote to known or delete
        if action in ('promote_unknown', 'delete_unknown'):
            with settings_lock:
                unknown_manifest_path = str(
                    face_detection_config.get(
                        'manifest_embed_path',
                        os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json')
                    )
                )
            uid = (request.form.get('uid') or '').strip()
            if uid:
                entries = _load_embed_manifest(unknown_manifest_path)
                if action == 'promote_unknown':
                    name = (request.form.get('name') or '').strip()
                    if name:
                        pick = None
                        for e in entries:
                            if str(e.get('uid', '')) == uid:
                                pick = e
                                break
                        if pick is not None:
                            try:
                                _append_known_manifest(
                                    KNOWN_EMBED_PATH,
                                    {"name": name, "embedding": pick.get('embedding', []), "ts": pick.get('ts', 0), "path": pick.get('path', '')}
                                )
                            except Exception:
                                pass
                            # Remove from unknown manifest
                            new_entries = [e for e in entries if str(e.get('uid', '')) != uid]
                            try:
                                _write_embed_manifest(unknown_manifest_path, new_entries)
                            except Exception:
                                pass
                elif action == 'delete_unknown':
                    new_entries = []
                    img_path = None
                    for e in entries:
                        if str(e.get('uid', '')) == uid:
                            img_path = e.get('path')
                            continue
                        new_entries.append(e)
                    try:
                        _write_embed_manifest(unknown_manifest_path, new_entries)
                    except Exception:
                        pass
                    if img_path:
                        try:
                            os.remove(img_path)
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
                    _save_config(CONFIG_PATH, object_detection_config, motion_detection_config, face_detection_config, auth_config=auth_config)
                    logger.info("Auth config saved successfully")
                except Exception as e:
                    logger.error(f"Failed to save auth config: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            return redirect(url_for('settings'))

        select_all_flag = ('select_all' in request.form)
        selected = set(request.form.getlist('classes'))
        face_archive_flag = ('face_archive_unknown' in request.form)
        face_dedup_flag = ('face_dedup_enabled' in request.form)
        dedup_method_in = request.form.get('face_dedup_method', '').strip().lower()
        embed_thr_in = request.form.get('face_embedding_threshold', '')
        min_dur_in = request.form.get('face_min_duration_sec', '')

        # Read motion detection sensitivity values with fallbacks
        def _to_int(val, default):
            try:
                return int(val)
            except Exception:
                return default

        th_in = _to_int(request.form.get('md_threshold', ''), motion_detection_config['threshold'])
        ma_in = _to_int(request.form.get('md_min_area', ''), motion_detection_config['min_area'])
        ke_in = _to_int(request.form.get('md_kernel', ''), motion_detection_config['kernel'])
        it_in = _to_int(request.form.get('md_iterations', ''), motion_detection_config['iterations'])
        pd_in = _to_int(request.form.get('md_pad', ''), motion_detection_config['pad'])

        # Clamp to sane ranges
        th_in = max(0, min(255, th_in))
        ma_in = max(0, ma_in)
        ke_in = max(1, ke_in)
        it_in = max(0, it_in)
        pd_in = max(0, pd_in)

        with settings_lock:
            # YOLO class selection
            object_detection_config['select_all'] = select_all_flag
            object_detection_config['classes'] = selected
            # Motion sensitivity
            motion_detection_config['threshold'] = th_in
            motion_detection_config['min_area'] = ma_in
            motion_detection_config['kernel'] = ke_in
            motion_detection_config['iterations'] = it_in
            motion_detection_config['pad'] = pd_in
            # Face detection
            face_detection_config['archive_unknown'] = bool(face_archive_flag)
            face_detection_config['dedup_enabled'] = bool(face_dedup_flag)
            # Optional controls (we'll provide sliders in UI; keep defaults if absent)
            dd_th = request.form.get('face_dedup_threshold')
            cd_min = request.form.get('face_cooldown_minutes')
            try:
                if dd_th is not None and dd_th != '':
                    face_detection_config['dedup_threshold'] = max(0, min(64, int(dd_th)))
            except Exception:
                pass
            try:
                if cd_min is not None and cd_min != '':
                    face_detection_config['cooldown_minutes'] = max(0, int(cd_min))
            except Exception:
                pass
            try:
                if min_dur_in is not None and min_dur_in != '':
                    face_detection_config['min_duration_sec'] = max(1, int(min_dur_in))
            except Exception:
                pass
            # Dedup method and embedding threshold
            if dedup_method_in in ('embedding', 'phash'):
                face_detection_config['dedup_method'] = dedup_method_in
            try:
                if embed_thr_in is not None and embed_thr_in != '':
                    face_detection_config['embedding_threshold'] = max(0.0, min(2.0, float(embed_thr_in)))
            except Exception:
                pass
            # Ensure archive directory exists if enabling
            if face_detection_config['archive_unknown']:
                try:
                    os.makedirs(face_detection_config['archive_dir'], exist_ok=True)
                except Exception:
                    pass
        # Persist config to disk after general update
        try:
            _save_config(CONFIG_PATH, object_detection_config, motion_detection_config, face_detection_config)
        except Exception:
            pass
        return redirect(url_for('settings'))

    with settings_lock:
        select_all_flag = object_detection_config['select_all']
        selected = set(object_detection_config['classes'])
        m_thresh = motion_detection_config['threshold']
        m_min_area = motion_detection_config['min_area']
        m_kernel = motion_detection_config['kernel']
        m_iters = motion_detection_config['iterations']
        m_pad = motion_detection_config['pad']
        f_archive = bool(face_detection_config['archive_unknown'])
        f_min_dur = int(face_detection_config['min_duration_sec'])
        f_dir = face_detection_config['archive_dir']
        f_dedup = bool(face_detection_config.get('dedup_enabled', True))
        f_dd_th = int(face_detection_config.get('dedup_threshold', 10))
        f_cool = int(face_detection_config.get('cooldown_minutes', 60))
        f_method = str(face_detection_config.get('dedup_method', 'embedding'))
        f_embed_th = float(face_detection_config.get('embedding_threshold', 0.6))

    # Build unknowns list for settings management
    with settings_lock:
        unknown_manifest_path = str(face_detection_config.get('manifest_embed_path', os.path.join(BASE_DIR, 'archives', 'unknown_faces', 'manifest_embeddings.json')))
    try:
        unk_entries = _load_embed_manifest(unknown_manifest_path)
    except Exception:
        unk_entries = []
    unknowns_for_ui = []
    for e in unk_entries[:50]:
        p = e.get('path', '')
        unknowns_for_ui.append({
            'uid': e.get('uid', ''),
            'ts': e.get('ts', ''),
            'img_url': url_for('archives_image') + f"?path={p}" if p else ''
        })

    # Snapshot simple route health/status
    has_frame = (camera_stream.get_frame() is not None)
    raw_ok = camera_stream.running and has_frame
    motion_ok = raw_ok  # motion depends on camera frames
    objects_ok = (model is not None) and raw_ok
    faces_ok = (get_face_cascade() is not None) and raw_ok

    page_html = render_settings_page(
        names=names,
        select_all_flag=select_all_flag,
        selected=selected,
        m_thresh=m_thresh,
        m_min_area=m_min_area,
        m_kernel=m_kernel,
        m_iters=m_iters,
        m_pad=m_pad,
        f_archive=f_archive,
        f_min_dur=f_min_dur,
        f_dir=f_dir,
        f_dedup=f_dedup,
        f_dd_th=f_dd_th,
        f_cool=f_cool,
        f_method=f_method,
        f_embed_th=f_embed_th,
        raw_ok=raw_ok,
        motion_ok=motion_ok,
        objects_ok=objects_ok,
        faces_ok=faces_ok,
        face_recognition_available=face_recognition_available,
        unknowns=unknowns_for_ui,
        device_id=str(DEVICE_ID or ''),
        port=int(APP_PORT),
        mdns_enabled=(not MDNS_DISABLE),
        app_version=str(APP_VERSION),
        auth_mode=str(auth_config.get('auth_mode', 'local')),
        oauth2_base_url=str(auth_config.get('oauth2_base_url', '')),
        oauth2_client_id=str(auth_config.get('oauth2_client_id', '')),
        oauth2_client_secret=str(auth_config.get('oauth2_client_secret', '')),
        oauth2_scope=str(auth_config.get('oauth2_scope', 'openid profile email offline_access')),
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


@app.route('/video_feed_objects')
def video_feed_objects():
    """Video streaming route - YOLOv8n object detection overlay"""
    resp = Response(generate_frames_with_objects(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp

@app.route('/video_feed_faces')
def video_feed_faces():
    """Video streaming route - face detection overlay (Haar)."""
    resp = Response(generate_frames_with_faces(),
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
