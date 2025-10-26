# 🚀 Pi Zero W Quick Start Guide

## Get OpenSentry - SMV running on Raspberry Pi Zero W in 5 minutes

---

## Prerequisites

1. Raspberry Pi Zero W with Raspberry Pi OS installed
2. USB camera or Raspberry Pi Camera Module
3. Internet connection
4. SSH access to your Pi

---

## Step 1: Install Docker (if not already installed)

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
```

---

## Step 2: Clone Repository

```bash
cd ~
git clone https://github.com/Sbussiso/OpenSentry-SMV.git
cd OpenSentry-SMV
```

---

## Step 3: Start in Snapshot Mode

```bash
# Build and start (first time will take 10-15 minutes on Pi Zero W)
docker compose -f compose-snapshot.yaml up -d

# Watch the logs
docker logs -f opensentry-snapshot
```

**Wait for**: `"SnapshotWorker started (interval-based capture mode)"`

---

## Step 4: Access Web Interface

Open browser to:
- **Local**: `http://raspberrypi.local:5000`
- **By IP**: `http://192.168.1.xxx:5000`

**Login**:
- Username: `admin`
- Password: `admin`

---

## Step 5: Verify It's Working

You should see:
- ✅ "Latest Snapshot" refreshing every 10 seconds
- ✅ Snapshot gallery filling with images
- ✅ Motion detection working (move in front of camera)
- ✅ CPU usage under 20% (`docker stats`)

---

## Troubleshooting

### No camera detected
```bash
# Check camera is connected
ls -l /dev/video*

# Test camera manually
sudo apt-get install v4l-utils
v4l2-ctl --list-devices
```

### High CPU usage
Edit `compose-snapshot.yaml`:
```yaml
- OPENSENTRY_SNAPSHOT_INTERVAL=20    # Increase to 20 seconds
- OPENSENTRY_CAMERA_WIDTH=240        # Lower resolution
- OPENSENTRY_CAMERA_HEIGHT=180
```

Then restart:
```bash
docker compose -f compose-snapshot.yaml restart
```

### No snapshots appearing
```bash
# Check logs for errors
docker logs opensentry-snapshot

# Check snapshot directory
ls -lh snapshots/

# Verify disk space
df -h
```

---

## Configuration

### Change Capture Interval

Edit `compose-snapshot.yaml`:
```yaml
environment:
  - OPENSENTRY_SNAPSHOT_INTERVAL=15  # Capture every 15 seconds
```

Restart container:
```bash
docker compose -f compose-snapshot.yaml restart
```

### Change Retention

Edit `config.json` (create if doesn't exist):
```json
{
  "snapshot_mode": {
    "enabled": true,
    "interval": 10,
    "retention_count": 50,
    "retention_days": 3
  }
}
```

Restart container.

---

## Performance Tips for Pi Zero W

### Ultra Low Power Mode
```yaml
environment:
  - OPENSENTRY_SNAPSHOT_INTERVAL=20    # Longer intervals
  - OPENSENTRY_CAMERA_WIDTH=240        # Lower resolution
  - OPENSENTRY_CAMERA_HEIGHT=180
  - OPENSENTRY_JPEG_QUALITY=50         # Lower quality
  - OPENSENTRY_CAMERA_FPS=3            # Minimum FPS
```

### Mount External Storage (USB drive)
```yaml
volumes:
  - /mnt/usb/snapshots:/app/snapshots
```

---

## Useful Commands

```bash
# View logs
docker logs -f opensentry-snapshot

# Restart
docker compose -f compose-snapshot.yaml restart

# Stop
docker compose -f compose-snapshot.yaml down

# Check resource usage
docker stats opensentry-snapshot

# View latest snapshots
ls -lth snapshots/ | head -10

# Count snapshots
ls snapshots/*.jpg | wc -l
```

---

## Expected Performance

On Raspberry Pi Zero W:
- **CPU Usage**: 10-20%
- **Memory Usage**: 50-80MB
- **Capture Rate**: 1 snapshot every 10-20 seconds
- **Stability**: 24/7 operation ✅
- **Storage**: ~2MB for 100 snapshots at 320x240

---

## Security Recommendations

### Change Default Password

Edit `compose-snapshot.yaml`:
```yaml
environment:
  - OPENSENTRY_USER=yourusername
  - OPENSENTRY_PASS=yourpassword
  - OPENSENTRY_SECRET=generate-a-long-random-string-here
```

Restart container.

### Enable HTTPS

Use a reverse proxy like Caddy:
```bash
sudo apt install caddy
```

Create `/etc/caddy/Caddyfile`:
```
raspberrypi.local {
    reverse_proxy localhost:5000
}
```

---

## Battery Power Setup

For battery-powered deployments:

1. Use USB power bank (10,000mAh recommended)
2. Increase snapshot interval to 30-60 seconds
3. Consider adding PIR sensor for wake-on-motion (future feature)

Expected battery life:
- 10,000mAh @ 20s interval: **8-12 hours**
- 20,000mAh @ 30s interval: **20-24 hours**

---

## Next Steps

1. ✅ Test motion detection by moving in front of camera
2. ✅ Adjust capture interval and retention settings
3. ✅ Set up remote access (port forwarding or VPN)
4. ✅ Configure automatic backups of snapshots
5. ✅ Change default password!

---

## Getting Help

- **Full Documentation**: [README.md](README.md)
- **Detailed Guide**: [SNAPSHOT_MODE.md](SNAPSHOT_MODE.md)
- **Implementation Details**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Issues**: [GitHub Issues](https://github.com/Sbussiso/OpenSentry-SMV/issues)

---

## Success! 🎉

Your Raspberry Pi Zero W is now a motion detection security camera!

Access the gallery at: **http://raspberrypi.local:5000**

---

*OpenSentry - SMV: Making security accessible on any device.*
