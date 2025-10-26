# OpenSentry - SMV (Snapshot Motion Version)

## Snapshot-Only Mode for Low-Power Devices

OpenSentry - SMV is optimized for resource-constrained devices like the **Raspberry Pi Zero W**, **Pi Zero 2 W**, and other low-power hardware.

Instead of continuous video streaming, snapshot mode captures images at configurable intervals, dramatically reducing CPU, memory, and power consumption.

---

## 🎯 Key Features

- **Interval-based capture** - Take snapshots every 5-60 seconds (configurable)
- **Simple motion detection** - Lightweight frame differencing instead of MOG2
- **Automatic retention** - Keep last N snapshots or X days
- **Gallery UI** - Browse, view, and download snapshots
- **Ultra-low resource usage** - 10-30% CPU vs 80-100% in streaming mode

---

## 📊 Performance Comparison

| Metric | Streaming Mode (LMV) | Snapshot Mode (SMV) |
|--------|---------------------|---------------------|
| CPU Usage | 80-100% | 10-30% |
| Memory | 150-200MB | 50-80MB |
| Network | Continuous | Minimal |
| Storage | N/A | 10-50MB/day |
| Pi Zero W | ❌ Not usable | ✅ Works! |
| Pi Zero 2 W | ⚠️ Laggy | ✅ Smooth |

---

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/Sbussiso/OpenSentry-SMV.git
cd OpenSentry-SMV

# Use the snapshot-optimized compose file
docker compose -f compose-snapshot.yaml up -d

# View logs
docker logs -f opensentry-snapshot

# Access at http://raspberrypi.local:5000
```

### Option 2: Environment Variables

Add to your existing `compose.yaml`:

```yaml
environment:
  - OPENSENTRY_SNAPSHOT_MODE=1
  - OPENSENTRY_SNAPSHOT_INTERVAL=10
  - OPENSENTRY_CAMERA_WIDTH=320
  - OPENSENTRY_CAMERA_HEIGHT=240
  - OPENSENTRY_CAMERA_FPS=5
  - OPENSENTRY_JPEG_QUALITY=60
```

### Option 3: Configuration File

Copy the example config:

```bash
cp config-snapshot-example.json config.json
```

Edit `config.json` to enable snapshot mode:

```json
{
  "snapshot_mode": {
    "enabled": true,
    "interval": 10,
    "motion_detection": true,
    "simple_motion": true,
    "retention_count": 100,
    "retention_days": 7
  }
}
```

---

## ⚙️ Configuration Options

### Snapshot Mode Settings

| Setting | Description | Default | Range |
|---------|-------------|---------|-------|
| `enabled` | Enable snapshot-only mode | `false` | boolean |
| `interval` | Seconds between captures | `10` | 5-60 |
| `motion_detection` | Enable motion detection | `true` | boolean |
| `simple_motion` | Use lightweight frame diff | `true` | boolean |
| `retention_count` | Max snapshots to keep | `100` | 10-1000 |
| `retention_days` | Max age in days | `7` | 1-30 |

### Camera Settings (for Pi Zero W)

```yaml
environment:
  - OPENSENTRY_CAMERA_WIDTH=320        # 320x240 for Pi Zero W
  - OPENSENTRY_CAMERA_HEIGHT=240       # 640x480 for Pi Zero 2 W+
  - OPENSENTRY_CAMERA_FPS=5            # 5-10 fps recommended
  - OPENSENTRY_CAMERA_MJPEG=1          # Use hardware MJPEG
```

### JPEG Compression

```yaml
environment:
  - OPENSENTRY_JPEG_QUALITY=60         # 50-70 for low-power
  - OPENSENTRY_OUTPUT_MAX_WIDTH=640    # Limit output size
```

---

## 🖥️ User Interface

### Snapshot Gallery

When in snapshot mode, the web UI automatically switches to a gallery view:

- **Latest snapshot** - Auto-refreshes every 10 seconds
- **Statistics** - Total snapshots, motion events, capture interval
- **Thumbnail grid** - Browse recent snapshots
- **Full-size modal** - Click any thumbnail to view details
- **Download** - Save snapshots to your device

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Snapshot gallery UI |
| `/api/snapshots/latest` | GET | Get latest snapshot (JPEG) |
| `/api/snapshots/list` | GET | List all snapshots (JSON) |
| `/api/snapshots/image/<filename>` | GET | Get specific snapshot |
| `/api/snapshots/delete/<filename>` | POST/DELETE | Delete a snapshot |
| `/api/snapshot` | GET | Download current snapshot |

---

## 📱 Device Recommendations

### Raspberry Pi Zero W (512MB, 1-core)
```yaml
OPENSENTRY_CAMERA_WIDTH=320
OPENSENTRY_CAMERA_HEIGHT=240
OPENSENTRY_CAMERA_FPS=5
OPENSENTRY_SNAPSHOT_INTERVAL=15
OPENSENTRY_JPEG_QUALITY=50
```
**Expected Performance**: 10-20% CPU, ~60MB RAM, 1 snapshot every 15 seconds

### Raspberry Pi Zero 2 W (512MB, 4-core)
```yaml
OPENSENTRY_CAMERA_WIDTH=640
OPENSENTRY_CAMERA_HEIGHT=480
OPENSENTRY_CAMERA_FPS=10
OPENSENTRY_SNAPSHOT_INTERVAL=10
OPENSENTRY_JPEG_QUALITY=60
```
**Expected Performance**: 15-25% CPU, ~80MB RAM, 1 snapshot every 10 seconds

### Raspberry Pi 3B/3B+ (1GB, 4-core)
```yaml
OPENSENTRY_CAMERA_WIDTH=640
OPENSENTRY_CAMERA_HEIGHT=480
OPENSENTRY_CAMERA_FPS=15
OPENSENTRY_SNAPSHOT_INTERVAL=5
OPENSENTRY_JPEG_QUALITY=70
```
**Expected Performance**: 10-15% CPU, ~100MB RAM, 1 snapshot every 5 seconds

---

## 🔧 Advanced Configuration

### Custom Snapshot Directory

Mount external storage for more capacity:

```yaml
volumes:
  - /mnt/usb/snapshots:/app/snapshots
```

### Motion Detection Tuning

Edit `config.json`:

```json
{
  "motion_detection": {
    "min_area": 300,         // Lower = more sensitive
    "pad": 8                 // Bounding box padding
  }
}
```

### Automatic Cleanup

Snapshots are automatically cleaned up based on:
- `retention_count` - Maximum number to keep
- `retention_days` - Maximum age in days

Cleanup runs every 10 captures.

---

## 📊 Storage Estimates

| Resolution | Quality | Size/Image | 100 Images | 1000 Images |
|-----------|---------|------------|------------|-------------|
| 320x240 | 50% | ~15KB | ~1.5MB | ~15MB |
| 320x240 | 70% | ~25KB | ~2.5MB | ~25MB |
| 640x480 | 60% | ~40KB | ~4MB | ~40MB |
| 640x480 | 80% | ~65KB | ~6.5MB | ~65MB |

**Example**: At 10-second intervals with 100-image retention (320x240 @ 60%), you'll use ~2MB storage and capture ~8,640 images per day.

---

## 🐛 Troubleshooting

### Snapshots not being captured

```bash
# Check logs
docker logs -f opensentry-snapshot

# Verify snapshot mode is enabled
docker exec opensentry-snapshot env | grep SNAPSHOT

# Check camera status
docker exec opensentry-snapshot ls -la /dev/video*
```

### High CPU usage even in snapshot mode

- Lower camera resolution (try 320x240)
- Increase snapshot interval (try 15-20 seconds)
- Disable motion detection: `OPENSENTRY_SNAPSHOT_MODE_MOTION=0`
- Reduce JPEG quality (try 50%)

### Gallery not updating

- Check `/api/snapshots/list` endpoint
- Verify snapshots directory is writable
- Clear browser cache (Ctrl+Shift+R)

### Out of storage

```bash
# Check disk usage
df -h

# Manually clean old snapshots
rm -f /path/to/snapshots/*_snapshot.jpg

# Or lower retention settings in config.json
```

---

## 🔄 Switching Between Modes

### Enable Snapshot Mode

```bash
# Via environment variable
docker compose -f compose-snapshot.yaml up -d

# Via config file
echo '{"snapshot_mode": {"enabled": true}}' > config.json
docker compose restart
```

### Disable Snapshot Mode (return to streaming)

```bash
# Remove environment variable
# Use standard compose.yaml
docker compose -f compose.yaml up -d

# Or edit config.json
{"snapshot_mode": {"enabled": false}}
```

---

## 🌟 Use Cases

### Home Security on a Budget
- Pi Zero W + USB camera + 16GB SD card
- Captures motion events 24/7
- View snapshots remotely via network
- Total cost: ~$20-30

### Wildlife Camera
- Pi Zero W + battery pack + camera
- 10-hour battery life with snapshot mode
- Automatic cleanup keeps storage lean
- PIR sensor trigger (future feature)

### Time-Lapse Photography
- Capture interval photos for time-lapse
- Automatic retention management
- Download entire gallery as ZIP (future feature)
- Motion filtering optional

---

## 📚 Further Reading

- [Main README](README.md) - Full project documentation
- [Docker Deployment](README.md#docker-deployment) - Container setup
- [API Documentation](README.md#api--endpoints) - REST API reference
- [Troubleshooting Guide](README.md#troubleshooting) - Common issues

---

## 🤝 Contributing

Found a bug or have a feature request for snapshot mode? Please open an issue!

---

**OpenSentry - SMV**: Making motion detection accessible on any device.
