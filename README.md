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
      - "5000:5000"
    environment:
      - OPENSENTRY_USER=admin
      - OPENSENTRY_PASS=admin
      - OPENSENTRY_SECRET=please-change-me
      - OPENSENTRY_LOG_LEVEL=INFO
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
- OPENSENTRY_PORT=5000       (metadata only; container listens on 5000)
- OPENSENTRY_DEVICE_NAME=OpenSentry  (shown in header and mDNS TXT)
- OPENSENTRY_API_TOKEN=      (if set, `/status` requires Authorization: Bearer <token>)
- OPENSENTRY_MDNS_DISABLE=0  (set to 1 to disable mDNS advertisement)
- OPENSENTRY_VERSION=0.1.0   (metadata only for discovery)

Config and archives
-------------------
- `config.json` persists motion/object/face settings and a generated `device_id`.
- `archives/` stores snapshots of unknown faces and manifests.
- Both are ignored by Git (see `.gitignore`).

Security notes
--------------
- Change OPENSENTRY_USER/OPENSENTRY_PASS/OPENSENTRY_SECRET in production.
- Use strong secrets and consider HTTPS termination in front of the app.
- Health endpoint at `/health` is unauthenticated for probes.

Camera selection
----------------
- The app reads `OPENSENTRY_CAMERA_INDEX` (default 0) and auto-probes indices 0..5 until a working device is found.
- In Docker, map the device node(s) into the container, e.g. `/dev/video0:/dev/video0` and add `group_add: [video]`.
  - Avoid `privileged: true` unless needed. Use it only as a last resort.

Endpoints
---------
- `/` – Index
- `/all_feeds` – 2x2 grid of streams
- `/video_feed`, `/video_feed_motion`, `/video_feed_objects`, `/video_feed_faces`
- `/settings` – Motion/face settings and unknowns management
- `/archives/unknown_faces` – Review and promote/delete unknown faces
- `/health` – Health check (200 OK)

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

Troubleshooting
---------------
- Can’t access camera in Docker? Ensure you’re talking to the system engine and the device exists inside the container.
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
- Zeroconf/mDNS not working? Ensure the container can broadcast on the LAN. You can disable advertisement with `OPENSENTRY_MDNS_DISABLE=1`.

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

