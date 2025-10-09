OpenSentry
===========

Turn any Linux device with a camera into a local security system you can view from your browser.

Features
--------
- Dark-themed UI with header and quick navigation
- Live streams: Raw, Motion, YOLO Objects, Faces (Haar)
- Settings page to tune motion/face behavior and manage unknown faces
- Archives of unknown faces with promote/delete actions
- Health endpoint and simple session auth
- **OAuth2 Authentication** – Optional integration with external OAuth2/OIDC providers

Requirements
------------
- Python 3.12+
- Linux with a V4L2 camera (e.g., /dev/video0)

Quickstart (host)
-----------------
1) Create env and run:
```bash
uv run server.py
# Visit http://127.0.0.1:5000
```

2) Default login
- Username: admin
- Password: admin
Set env vars below for production.

Quickstart (Docker Compose)
---------------------------
```bash
docker compose up -d
# Visit http://127.0.0.1:5000
```

The compose file publishes port 5000, maps archives to /app/archives, and (optionally) maps /dev/video0. Ensure you are using the system Docker engine (not Docker Desktop VM) to access host devices.

Example `compose.yaml`:

```yaml
services:
  opensentry:
    build:
      context: .
      dockerfile: Dockerfile
    image: opensentry:pi
    container_name: opensentry
    ports:
      - "${OPENSENTRY_PORT:-5000}:${OPENSENTRY_PORT:-5000}"
    environment:
      - OPENSENTRY_USER=admin
      - OPENSENTRY_PASS=admin
      - OPENSENTRY_SECRET=please-change-me
      - OPENSENTRY_LOG_LEVEL=INFO
      - OPENSENTRY_PORT=${OPENSENTRY_PORT:-5000}
      # Optional discovery metadata and protection for /status
      # - OPENSENTRY_DEVICE_NAME=Garage Cam
      # - OPENSENTRY_API_TOKEN=your-ci-or-command-token
      # - OPENSENTRY_MDNS_DISABLE=0
    volumes:
      - ./archives:/app/archives
    devices:
      - /dev/video0:/dev/video0
    group_add:
      - video
    restart: unless-stopped
```

Environment variables
---------------------
- OPENSENTRY_USER=admin
- OPENSENTRY_PASS=admin
- OPENSENTRY_SECRET=please-change-me
- OPENSENTRY_LOG_LEVEL=INFO  (INFO, DEBUG)
- OPENSENTRY_CAMERA_INDEX=0  (preferred index; auto-probes 0..5)
- OPENSENTRY_PORT=5000       (preferred HTTP port; app will fall back to the next free port if busy)
- OPENSENTRY_DEVICE_NAME=OpenSentry  (shown in header and mDNS TXT)
- OPENSENTRY_API_TOKEN=      (if set, `/status` requires Authorization: Bearer <token>)
- OPENSENTRY_MDNS_DISABLE=0  (set to 1 to disable mDNS advertisement)
- OPENSENTRY_VERSION=0.1.0   (metadata only for discovery)

Config and archives
-------------------
- `config.json` persists motion/object/face settings and a generated `device_id`.
- `archives/` stores snapshots of unknown faces and manifests.
- Both are ignored by Git (see `.gitignore`).

Authentication
--------------
OpenSentry supports two authentication modes:

### Local Authentication (Default)
- Simple username/password authentication
- Configure via environment variables:
  - `OPENSENTRY_USER=admin` (default: admin)
  - `OPENSENTRY_PASS=admin` (default: admin)
  - `OPENSENTRY_SECRET=please-change-me` (session encryption key)

### OAuth2 Authentication
- Integrate with external OAuth2/OIDC providers (e.g., custom OAuth2 server, Keycloak, Auth0, etc.)
- Configure via the Settings page (`/settings`):
  1. Select "OAuth2 Authentication" option
  2. Enter OAuth2 Server Base URL (e.g., `http://127.0.0.1:8000`)
  3. Enter Client ID (e.g., `opensentry-device`)
  4. Optional: Enter Client Secret (for confidential clients)
  5. Configure Scope (default: `openid profile email offline_access`)
  6. Click "Test OAuth2 Connection" to verify
  7. Click "Save Authentication Settings"
- Settings are persisted in `config.json` under the `auth` key
- OAuth2 flow uses Authorization Code + PKCE for security
- Local login fallback is available via `/oauth2/fallback` if OAuth2 server is unavailable

**Example OAuth2 Configuration:**
```json
{
  "auth": {
    "auth_mode": "oauth2",
    "oauth2_base_url": "http://127.0.0.1:8000",
    "oauth2_client_id": "opensentry-device",
    "oauth2_client_secret": "",
    "oauth2_scope": "openid profile email offline_access"
  }
}
```

Security notes
--------------
- Change OPENSENTRY_USER/OPENSENTRY_PASS/OPENSENTRY_SECRET in production.
- Use strong secrets and consider HTTPS termination in front of the app.
- Health endpoint at `/health` is unauthenticated for probes.
- When using OAuth2, ensure the OAuth2 server is properly secured and accessible.

Camera selection
----------------
- The app reads `OPENSENTRY_CAMERA_INDEX` (default 0) and auto-probes indices 0..5 until a working device is found.
- In Docker, map the device node(s) into the container, e.g. `/dev/video0:/dev/video0` and add `group_add: [video]`.
  - Avoid `privileged: true` unless needed. Use it only as a last resort.

Endpoints
---------
### Main Routes
- `/` – Index
- `/all_feeds` – 2x2 grid of streams
- `/video_feed`, `/video_feed_motion`, `/video_feed_objects`, `/video_feed_faces`
- `/settings` – Motion/face/authentication settings and unknowns management
- `/archives/unknown_faces` – Review and promote/delete unknown faces
- `/health` – Health check (200 OK)

### Authentication Routes
- `/login` – Local login (or redirects to OAuth2 if configured)
- `/logout` – Clear session and logout
- `/oauth2/login` – Initiate OAuth2 authorization flow
- `/oauth2/callback` – OAuth2 callback handler
- `/oauth2/fallback` – Enable local login fallback when OAuth2 is configured

### API Routes
- `/api/oauth2/test` – Test OAuth2 server connectivity (query param: `base_url`)

Discovery (mDNS + /status)
---------------------------
- mDNS service: `_opensentry._tcp.local` via Zeroconf.
- TXT keys (no secrets):
  - `id` (short persistent device id)
  - `name` (device display name)
  - `ver` (app version)
  - `caps` (raw,motion,objects,faces)
  - `auth` (token|session)
  - `api` (`/status,/health`)
  - `path` (`/`)
  - `proto` (`1`)

`/status` JSON:
```json
{
  "id": "abc123def456",
  "name": "OpenSentry",
  "version": "0.1.0",
  "port": 5000,
  "caps": ["raw","motion","objects","faces"],
  "routes": {"raw": true, "motion": true, "objects": true, "faces": true},
  "camera": {"running": true, "has_frame": true},
  "auth_mode": "token" | "session"
}
```

If `OPENSENTRY_API_TOKEN` is set, call with a bearer token:
```bash
curl -H "Authorization: Bearer $OPENSENTRY_API_TOKEN" http://<ip>:5000/status
```

OAuth2 Integration Example
---------------------------
OpenSentry can integrate with the custom OAuth2 server from the sibling `Oauth2` project or any OIDC-compliant provider.

### Using the Custom OAuth2 Server
1. Start the OAuth2 server:
   ```bash
   cd ../Oauth2
   uv run server.py
   # Server runs at http://127.0.0.1:8000
   ```

2. Register OpenSentry as a client in the OAuth2 server's `config.json`:
   ```json
   {
     "clients": {
       "opensentry-device": {
         "client_secret": null,
         "redirect_uris": ["http://localhost:5000/oauth2/callback"],
         "scopes": ["openid", "profile", "email"],
         "is_confidential": false
       }
     }
   }
   ```

3. Configure OpenSentry via `/settings`:
   - Auth Mode: OAuth2 Authentication
   - OAuth2 Server Base URL: `http://127.0.0.1:8000`
   - Client ID: `opensentry-device`
   - Client Secret: (leave empty for public client)
   - Scope: `openid profile email offline_access`

4. Test the connection and save settings
5. You'll be redirected to the OAuth2 server for login
6. After successful authentication, you'll be redirected back to OpenSentry

### Multiple Device Instances with OAuth2
When running multiple OpenSentry instances with OAuth2:
- Each instance needs its own client ID registered in the OAuth2 server
- Update `redirect_uris` to match each instance's port:
  ```json
  {
    "clients": {
      "opensentry-garage": {
        "redirect_uris": ["http://localhost:5000/oauth2/callback"]
      },
      "opensentry-front": {
        "redirect_uris": ["http://localhost:5001/oauth2/callback"]
      }
    }
  }
  ```

Port selection and multiple instances
-------------------------------------
- The server binds to `OPENSENTRY_PORT` (default `5000`). If that port is busy, it tries `+1` up to 10 attempts (e.g., 5001, 5002...).
- `/status` and the mDNS advertisement include the actual bound `port`.
- Docker Compose: the example maps host and container ports using the same `OPENSENTRY_PORT` value so discovery matches host reachability.
- To run multiple instances on one host (Compose):
  ```bash
  OPENSENTRY_PORT=5000 docker compose -p opensentry5000 up -d --build
  OPENSENTRY_PORT=5001 docker compose -p opensentry5001 up -d --build
  ```
  Then visit `http://<host>:5000` and `http://<host>:5001` respectively.

Troubleshooting
---------------

### Camera Issues
- Can't access camera in Docker? Ensure you're talking to the system engine and the device exists inside the container.
  - Check context: `docker context show` → should be `default`
  - If needed, force the system socket: `DOCKER_HOST=unix:///var/run/docker.sock`
  - Test mapping directly:
    ```bash
    docker run --rm -it --device /dev/video0:/dev/video0 ubuntu:22.04 ls -l /dev/video0
    ```
- Streams blank? Check logs and set `OPENSENTRY_LOG_LEVEL=DEBUG`.
  ```bash
  docker logs -n 200 opensentry
  ```

### Network Issues
- Zeroconf/mDNS not working? Ensure the container can broadcast on the LAN. You can disable advertisement with `OPENSENTRY_MDNS_DISABLE=1`.

### OAuth2 Issues
- **"OAuth2 Server Unavailable"**: Verify the OAuth2 server is running and accessible from OpenSentry:
  ```bash
  curl http://127.0.0.1:8000/.well-known/openid-configuration
  ```
- **"Invalid OAuth2 callback"**: Ensure the redirect URI in OAuth2 server config matches OpenSentry's callback URL:
  - Format: `http://<host>:<port>/oauth2/callback`
  - Example: `http://localhost:5000/oauth2/callback`
- **"Token exchange failed"**: Check OAuth2 server logs for details. Common causes:
  - Client ID mismatch
  - Invalid client secret (if using confidential client)
  - Redirect URI mismatch
  - PKCE verification failure
- **Locked out after switching to OAuth2**: Use the fallback URL to login with local credentials:
  ```
  http://localhost:5000/oauth2/fallback
  ```
- **Session lost during OAuth2 flow**: Ensure `OPENSENTRY_SECRET` is set and consistent across restarts. The secret is used to sign state tokens.

Continuous Integration
----------------------
- GitHub Actions builds the Docker image and validates:
  - `/health` is 200.
  - `/status` responds correctly in two modes:
    - without token
    - with a dummy token provided by the workflow
- Tests live in `tests/test_status.py`.

License
-------
MIT

