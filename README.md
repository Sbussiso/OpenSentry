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

Environment variables
---------------------
- OPENSENTRY_USER=admin
- OPENSENTRY_PASS=admin
- OPENSENTRY_SECRET=please-change-me
- OPENSENTRY_LOG_LEVEL=INFO
- OPENSENTRY_CAMERA_INDEX=0

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

License
-------
MIT (see LICENSE if present)

