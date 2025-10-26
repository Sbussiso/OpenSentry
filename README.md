# OpenSentry - SMV (Snapshot Motion Version)

**Turn any Linux device with a camera into an ultra-lightweight snapshot-based motion detection security system.**

Self-hosted. Privacy-first. **Snapshot-only**. Optimized for low-power devices. No cloud required.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

---

## 🎯 What is OpenSentry - SMV?

OpenSentry - SMV transforms any Linux device with a webcam into a **snapshot-based motion detection security camera**. Perfect for low-power devices like the Raspberry Pi Zero W, it captures images at intervals instead of streaming video, dramatically reducing resource usage.

### Key Features

- 📸 **Snapshot-Only** - Interval-based capture (5-60 seconds) - NO video streaming
- 🔋 **Ultra-Low Power** - 10-30% CPU usage on Pi Zero W
- 🚶 **Simple Motion Detection** - Lightweight frame differencing for overlay visualization
- 🖼️ **Gallery UI** - Browse, view, and download captured snapshots with auto-refresh
- 🗄️ **Automatic Retention** - Keep last N snapshots or X days with automatic cleanup
- 🔐 **Flexible Authentication** - Local auth or integrate with OAuth2/OIDC providers
- 🔍 **mDNS Discovery** - Auto-discover devices on your network
- 🐳 **Docker Ready** - Single-command deployment with Docker Compose

### Why Snapshot-Only?

By removing all video streaming infrastructure, OpenSentry - SMV achieves:

- **70-90% less CPU usage** compared to streaming solutions
- **60% less memory usage**
- **95% less network bandwidth**
- **5-10x longer battery life** for portable setups
- **Runs smoothly on Raspberry Pi Zero W** (1-core, 512MB RAM)

---

## 📖 Table of Contents

- [Quick Start](#-quick-start)
- [Hardware Requirements](#-hardware-requirements)
- [Installation](#-installation)
- [Configuration](#%EF%B8%8F-configuration)
- [Authentication](#-authentication)
- [API Endpoints](#-api-endpoints)
- [Discovery](#-discovery--mdns)
- [Troubleshooting](#-troubleshooting)
- [Related Projects](#-related-projects)

---

## 🚀 Quick Start

### Docker Deployment (Recommended)

```bash
# Clone the repository
git clone https://github.com/Sbussiso/OpenSentry-SMV.git
cd OpenSentry-SMV

# Start the application
docker compose up -d

# View logs
docker logs -f opensentry-smv

# Access at http://raspberrypi.local:5000 or http://localhost:5000
# Default credentials: admin / admin
```

That's it! OpenSentry is now capturing snapshots every 10 seconds with motion detection.

### Run from Source

```bash
# Install dependencies
uv sync

# Configure snapshot interval (optional)
export OPENSENTRY_SNAPSHOT_INTERVAL=10

# Start the server
uv run server.py

# Access at http://127.0.0.1:5000
```

**Note**: If you don't have a camera, set `OPENSENTRY_ALLOW_PLACEHOLDER=1` to test with a placeholder image.

### What You Get

- ✅ **Gallery UI** with auto-refreshing latest snapshot
- ✅ **Motion detection overlays** with lightweight frame differencing
- ✅ **Automatic retention** - keeps last 100 snapshots or 7 days
- ✅ **mDNS discovery** - find devices on your network automatically
- ✅ **Local or OAuth2 authentication**
- ✅ **Works on Pi Zero W** - 10-30% CPU usage

---

## 🖥️ Hardware Requirements

OpenSentry - SMV is **snapshot-only** - optimized for ultra-low power consumption.

### Raspberry Pi Models

| Model | CPU | RAM | Performance | CPU Usage | Notes |
|-------|-----|-----|-------------|-----------|-------|
| **Pi Zero W** | 1-core 1GHz ARMv6 | 512MB | ✅ **Works!** | 10-20% | **Primary target device** |
| **Pi Zero 2 W** | 4-core 1GHz ARMv8 | 512MB | ⭐⭐⭐⭐⭐ Excellent | <10% | Smooth, fast, highly recommended |
| **Pi 3B/3B+** | 4-core 1.2-1.4GHz ARMv8 | 1GB | ⭐⭐⭐⭐⭐ Excellent | <10% | More power than needed |
| **Pi 4/5** | 4-core 1.5-2.4GHz ARMv8 | 2-8GB | ⭐⭐⭐⭐⭐ Excellent | <5% | Overkill but works great |

### x86_64 / AMD64 (Intel/AMD PCs)

| Hardware | Performance | CPU Usage | Notes |
|----------|-------------|-----------|-------|
| **Desktop/Laptop** | ⭐⭐⭐⭐⭐ Excellent | <5% | Instant snapshots, near-zero impact |
| **Intel NUC / Mini PC** | ⭐⭐⭐⭐⭐ Excellent | <5% | Perfect for production deployments |
| **Old Desktop** (2010+) | ⭐⭐⭐⭐⭐ Excellent | 5-10% | Works perfectly, minimal resources |

### Our Recommendations

| Use Case | Recommended Hardware | Why |
|----------|---------------------|-----|
| **Ultra Budget** | Raspberry Pi Zero W | ✅ **$10-15** - Primary target, perfect for security |
| **Best Value** | Raspberry Pi Zero 2 W | ✅ **$15-20** - Excellent performance, fast snapshots |
| **Multiple Cameras** | Raspberry Pi 3B/3B+ | ✅ **$25-35** - Can run multiple instances |
| **Production** | Any x86_64 PC | ✅ **Existing hardware** - Minimal resource usage |

### Software Requirements
- Python 3.12+ (for source installation)
- Linux with V4L2 camera support (e.g., `/dev/video0`)
- Docker (optional, for containerized deployment)

---

## 📦 Installation

### Docker Deployment

The repo includes a `compose.yaml` preconfigured for optimal performance. **Recommended for all platforms.**

```bash
# Build and start the service
docker compose up -d --build

# Monitor logs
docker logs -f opensentry-smv

# Access at http://localhost:5000
```

**First-time setup on Raspberry Pi:**
```bash
git clone https://github.com/Sbussiso/OpenSentry-SMV.git
cd OpenSentry-SMV

# Build with ARM optimizations
docker compose build --no-cache
docker compose up -d

# Camera init takes 10-60s on Pi
docker logs -f opensentry-smv
```

### Run from Source

```bash
# Install dependencies with uv (recommended)
uv sync

# Or use pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start the server
uv run server.py
```

Visit **http://127.0.0.1:5000** and log in with `admin/admin`.

---

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENSENTRY_USER` | Local auth username | `admin` |
| `OPENSENTRY_PASS` | Local auth password | `admin` |
| `OPENSENTRY_SECRET` | Session encryption key (use random 64-char string) | Random (dev only) |
| `OPENSENTRY_PORT` | HTTP port (auto-increments if busy) | `5000` |
| `OPENSENTRY_SNAPSHOT_INTERVAL` | Seconds between snapshots (5-60) | `10` |
| `OPENSENTRY_JPEG_QUALITY` | JPEG quality (30-95) | `75` |
| `OPENSENTRY_CAMERA_INDEX` | Preferred camera index | `0` |
| `OPENSENTRY_DEVICE_NAME` | Device display name | `OpenSentry` |
| `OPENSENTRY_LOG_LEVEL` | Logging verbosity (`INFO`, `DEBUG`) | `INFO` |
| `OPENSENTRY_MDNS_DISABLE` | Disable mDNS advertisement | `0` |
| `OPENSENTRY_ALLOW_PLACEHOLDER` | Test without camera | `0` |
| `GUNICORN_WORKERS` | Number of Gunicorn workers | `1` |
| `GUNICORN_WORKER_CLASS` | Worker type (`sync` for snapshot-only) | `sync` |
| `GUNICORN_TIMEOUT` | Worker timeout in seconds | `120` |

### config.json Structure

```json
{
  "device_id": "a7077099be8a",
  "motion_detection": {
    "min_area": 500,
    "pad": 10
  },
  "snapshot_config": {
    "interval": 10,
    "motion_detection": true,
    "retention_count": 100,
    "retention_days": 7,
    "directory": "snapshots"
  },
  "auth": {
    "auth_mode": "local",
    "oauth2_base_url": "",
    "oauth2_client_id": "",
    "oauth2_client_secret": "",
    "oauth2_scope": "openid profile email offline_access"
  }
}
```

**Snapshot Configuration:**
- `interval` - Seconds between captures (5-60)
- `motion_detection` - Enable motion detection overlay on snapshots
- `retention_count` - Maximum number of snapshots to keep (default: 100)
- `retention_days` - Maximum age of snapshots in days (default: 7)
- `directory` - Directory to save snapshots (default: "snapshots")

**Motion Detection Parameters:**
- `min_area` - Minimum contour area in pixels to trigger detection (default: 500)
- `pad` - Padding around detection boxes in pixels (default: 10)

---

## 🔐 Authentication

OpenSentry supports two authentication modes: **Local** (simple username/password) and **OAuth2** (enterprise SSO integration).

### Local Authentication (Default)

Simple username/password authentication for quick setups.

**Configuration:**
```bash
# Environment variables
export OPENSENTRY_USER=admin
export OPENSENTRY_PASS=secure-password
export OPENSENTRY_SECRET=please-change-me
```

**Docker:**
```yaml
environment:
  - OPENSENTRY_USER=admin
  - OPENSENTRY_PASS=secure-password
  - OPENSENTRY_SECRET=random-64-char-secret
```

### OAuth2 Integration

Integrate with external OAuth2/OIDC providers for centralized authentication, SSO, and enterprise identity management.

**Supported Providers:**
- ✅ Custom OAuth2 Server ([see our OAuth2 project](#-related-projects))
- ✅ Keycloak
- ✅ Auth0
- ✅ Okta
- ✅ Google OAuth2
- ✅ Any OIDC-compliant provider

**Configuration via Web UI:**

1. Navigate to **Settings** → **Authentication**
2. Select **"OAuth2 Authentication"**
3. Enter your OAuth2 server details:
   - **Base URL**: `http://127.0.0.1:8000` (or your OAuth2 server address)
   - **Client ID**: `opensentry-device`
   - **Client Secret**: (optional, for confidential clients)
   - **Scope**: `openid profile email offline_access`
4. Click **"Test OAuth2 Connection"** to verify
5. Click **"Save Authentication Settings"**
6. Restart OpenSentry

**Fallback to Local Login:**

If the OAuth2 server is unavailable, users can access local login via:
```
http://your-opensentry:5000/oauth2/fallback
```

---

## 🌐 API Endpoints

### Main Routes

| Endpoint | Description | Auth Required |
|----------|-------------|---------------|
| `/` | Snapshot gallery dashboard | ✅ |
| `/settings` | Configuration page | ✅ |
| `/health` | Health check (200 OK) | ❌ |

### Authentication Routes

| Endpoint | Description |
|----------|-------------|
| `/login` | Local login page |
| `/logout` | Clear session and logout |
| `/oauth2/login` | Initiate OAuth2 authorization flow |
| `/oauth2/callback` | OAuth2 callback handler |
| `/oauth2/fallback` | Enable local login fallback |

### API Routes

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/status` | GET | Device status JSON | ❌ |
| `/api/snapshots/latest` | GET | Get the latest snapshot image | ✅ |
| `/api/snapshots/list` | GET | List all snapshots with metadata | ✅ |
| `/api/snapshots/image/<filename>` | GET | Retrieve a specific snapshot | ✅ |
| `/api/snapshots/delete/<filename>` | DELETE | Delete a snapshot | ✅ |
| `/api/oauth2/test` | GET | Test OAuth2 connectivity | ✅ |
| `/logs/download` | GET | Download server logs | ✅ |

**Example `/status` Response:**
```json
{
  "id": "a7077099be8a",
  "name": "OpenSentry",
  "version": "1.0.0",
  "port": 5000,
  "caps": ["snapshots"],
  "routes": {
    "snapshots": true
  },
  "camera": {
    "running": true,
    "has_frame": true
  },
  "auth_mode": "session"
}
```

---

## 🔍 Discovery & mDNS

OpenSentry advertises itself on the local network using mDNS (Zeroconf).

### mDNS Service

- **Service Type**: `_opensentry._tcp.local`
- **Port**: Actual bound port (may differ from `OPENSENTRY_PORT` if port was busy)

### TXT Records

| Key | Description | Example |
|-----|-------------|---------|
| `id` | Persistent device ID | `a7077099be8a` |
| `name` | Device display name | `Front Door Camera` |
| `ver` | OpenSentry version | `1.0.0` |
| `caps` | Capabilities | `snapshots` |
| `auth` | Auth mode | `session` |
| `api` | Available APIs | `/status,/health` |
| `path` | Web UI path | `/` |
| `proto` | Protocol version | `1` |

### Discovery Tools

Use the companion **OpenSentry Command** project to discover all devices on your network. See [Related Projects](#-related-projects).

---

## 🔧 Troubleshooting

### Raspberry Pi / ARM Issues

**Problem**: Camera initialization is slow on Raspberry Pi

**Solution**: This is normal. The Pi's camera takes 10-60 seconds to initialize. Check logs:
```bash
docker logs -f opensentry-smv
# Wait for: "INFO opensentry.camera: Opened camera device=/dev/video0"
```

**Problem**: High CPU usage on Raspberry Pi

**Solutions**:
1. Increase snapshot interval via settings (15-20 seconds for Pi Zero W)
2. Lower JPEG quality to 60-70%
3. Reduce camera resolution in Docker environment variables
4. Disable motion detection overlay if not needed

### Camera Issues

**Problem**: Camera not detected or blank snapshots

**Root Cause**: USB cameras often require privileged mode in Docker due to low-level device access requirements.

**Solution**: Enable privileged mode in `compose.yaml` (already enabled in default config):
```yaml
services:
  opensentry:
    privileged: true  # Required for camera access
    devices:
      - /dev/video0:/dev/video0
    group_add:
      - video
```

**Verify camera on host:**
```bash
ls -l /dev/video*
v4l2-ctl --list-devices
```

### OAuth2 Issues

**Problem**: "OAuth2 Server Unavailable"

**Solutions:**
1. Verify OAuth2 server is running:
   ```bash
   curl http://127.0.0.1:8000/.well-known/openid-configuration
   ```

2. Check network connectivity from OpenSentry to OAuth2 server

3. Use fallback: `http://127.0.0.1:5000/oauth2/fallback`

**Problem**: "Invalid OAuth2 callback" or redirect errors

**Solution**: Verify redirect URI matches exactly. Include both `localhost` and `127.0.0.1` variants:
```bash
redirect_uris = 'http://localhost:5000/oauth2/callback http://127.0.0.1:5000/oauth2/callback'
```

### Network Issues

**Problem**: mDNS/Zeroconf not working

**Solutions:**
1. Check if Avahi/Bonjour is running:
   ```bash
   sudo systemctl status avahi-daemon
   ```

2. Disable mDNS if not needed:
   ```bash
   export OPENSENTRY_MDNS_DISABLE=1
   ```

3. Docker: Use `network_mode: host` for better mDNS broadcasting

### Port Conflicts

**Problem**: Port 5000 already in use

**Solution**: OpenSentry auto-increments to next available port (5001, 5002, etc.)

To force a specific port:
```bash
export OPENSENTRY_PORT=5010
uv run server.py
```

---

## 🔗 Related Projects

### OpenSentry Command
**Device Discovery & Management Dashboard**

Central dashboard to discover, monitor, and manage all OpenSentry devices on your network.

- 🔍 Auto-discover devices via mDNS
- 📊 Network scanning and device status
- 🌐 Unified access to all cameras
- 🔐 OAuth2 integration for SSO

[View Project →](https://github.com/Sbussiso/OpenSentry-Command)

### LOauth2 (OAuth2 Server)
**Self-Hosted OAuth2 / OIDC Authorization Server**

Complete OAuth2/OIDC server for centralized authentication across all your services.

- 🔒 Enterprise-grade security (PKCE, refresh tokens, RS256)
- 🎛️ Admin UI for client management
- 🌐 Standards-compliant (OAuth 2.0, OIDC)
- 🚀 Production-ready

[View Project →](https://github.com/Sbussiso/LOauth2)

---

## 🤝 Contributing

Contributions welcome! Whether it's bug reports, feature requests, or code contributions.

- 🐛 **Report bugs**: [Open an issue](https://github.com/Sbussiso/OpenSentry-SMV/issues)
- 💡 **Request features**: [Start a discussion](https://github.com/Sbussiso/OpenSentry-SMV/discussions)
- 🔧 **Submit code**: Fork, develop, and create a pull request

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

**Free to use, modify, and deploy anywhere.**

---

## 🛡️ Security Best Practices

### For Production Deployments

- [ ] Change default credentials (`OPENSENTRY_USER`, `OPENSENTRY_PASS`)
- [ ] Generate strong random `OPENSENTRY_SECRET` (64+ characters)
- [ ] Use HTTPS with reverse proxy (nginx, Traefik, Caddy)
- [ ] Enable OAuth2 for centralized authentication
- [ ] Regular backups of `config.json`
- [ ] Keep dependencies updated (`uv sync` or `pip install --upgrade`)
- [ ] Monitor logs for unauthorized access attempts
- [ ] Use firewall rules to restrict access to trusted networks
- [ ] Disable mDNS in production (`OPENSENTRY_MDNS_DISABLE=1`)

### HTTPS Setup with Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name opensentry.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 🌟 Why OpenSentry - SMV?

- ✅ **Privacy-First** - All processing happens locally, no cloud required
- ✅ **Self-Hosted** - You control your data and infrastructure
- ✅ **Ultra-Lightweight** - Runs on Pi Zero W with 10-20% CPU usage
- ✅ **Flexible Authentication** - Start simple, scale with OAuth2/SSO
- ✅ **Network Discovery** - Auto-discover devices via mDNS
- ✅ **Open Source** - Audit, modify, and extend as needed
- ✅ **Production-Ready** - Stable, tested, and documented
- ✅ **Free Forever** - MIT license, no hidden costs

---

<p align="center">
  <strong>Take control of your security camera system.</strong><br>
  <em>Self-hosted. Private. Efficient.</em>
</p>

<p align="center">
  <a href="#-quick-start">Get Started →</a> |
  <a href="docs/SNAPSHOT_MODE.md">Documentation →</a> |
  <a href="#-related-projects">Related Projects →</a>
</p>
