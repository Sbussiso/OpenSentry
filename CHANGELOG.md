# Changelog

All notable changes to OpenSentry - SMV (Snapshot Motion Version) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-10-25

### Initial Release

OpenSentry - SMV (Snapshot Motion Version) is a complete reimagining of OpenSentry optimized for ultra-low-power devices like the Raspberry Pi Zero W.

### Added
- **Snapshot-only architecture** - Interval-based image capture (5-60 seconds configurable)
- **Lightweight motion detection** - Simple frame differencing algorithm for motion overlay
- **Snapshot gallery UI** - Auto-refreshing gallery with thumbnail grid and full-size viewer
- **Automatic retention management** - Count-based and age-based snapshot cleanup
- **Persistent snapshot storage** - Snapshots saved to configurable directory with Docker volume support
- **mDNS device discovery** - Auto-discover devices on local network via `_opensentry._tcp.local`
- **Flexible authentication** - Local username/password or OAuth2/OIDC integration
- **OAuth2 test endpoint** - Verify OAuth2 connectivity before saving settings
- **Settings UI** - Web-based configuration for snapshot interval, retention, and motion detection
- **Health endpoint** - `/health` for monitoring and health checks
- **Status endpoint** - `/status` for device information and capabilities
- **Diagnostics** - Download server logs via `/logs/download` endpoint
- **Docker support** - Production-ready Dockerfile and compose.yaml
- **Comprehensive documentation** - README, SNAPSHOT_MODE guide, and Pi Zero W quickstart

### Changed
- **Removed all video streaming** - No MJPEG streams, no continuous processing
- **Removed MOG2 background subtraction** - Replaced with lightweight frame differencing
- **Changed to sync worker mode** - Single Gunicorn worker with sync mode for snapshot-only operation
- **Simplified motion detection** - Only `min_area` and `pad` parameters (removed MOG2 parameters)
- **Optimized for Pi Zero W** - Achieves 10-20% CPU usage on 1-core, 512MB RAM device
- **Simplified configuration** - Removed video_config and stream_config, consolidated to snapshot_config
- **Updated dependency management** - Uses `uv` for fast, reliable dependency resolution

### Performance
- **70-90% less CPU usage** compared to streaming-based systems
- **60% less memory usage** - ~60MB on Pi Zero W
- **95% less network bandwidth** - Snapshots vs continuous MJPEG streams
- **5-10x longer battery life** for portable/battery-powered deployments

### Hardware Support
- **Raspberry Pi Zero W** - Primary target device (10-20% CPU)
- **Raspberry Pi Zero 2 W** - Excellent performance (<10% CPU)
- **Raspberry Pi 3/4/5** - Overkill but works perfectly (<5% CPU)
- **x86_64/AMD64** - Desktop/laptop/server support with near-zero overhead

### Security
- MIT License - Free and open source
- Local authentication with session management
- OAuth2/OIDC integration for enterprise deployments
- Configurable session secrets
- HTTPS-ready (use reverse proxy)

### Developer Experience
- Clean, modular codebase
- Type hints throughout
- Comprehensive error handling
- Detailed logging with configurable levels
- Docker development and production configs
- Automated snapshot cleanup
- Easy deployment with Docker Compose

---

## Version History

### [1.0.0] - 2025-10-25
- Initial public release of OpenSentry - SMV

---

## Migration from OpenSentry - LMV

OpenSentry - SMV is a complete rewrite focused on snapshot-only operation. Key differences:

| Feature | LMV (Live Motion Version) | SMV (Snapshot Motion Version) |
|---------|---------------------------|-------------------------------|
| **Video Streaming** | ✅ MJPEG streams | ❌ Removed entirely |
| **Motion Detection** | MOG2 background subtraction | Simple frame differencing |
| **Processing** | Continuous | Interval-based (5-60s) |
| **CPU Usage (Pi Zero W)** | 90-100% (unusable) | 10-20% |
| **Memory Usage** | ~180MB | ~60MB |
| **Target Hardware** | Pi 3/4 and above | Pi Zero W and above |
| **Use Case** | Real-time monitoring | Security snapshots, time-lapse |

For live video streaming requirements, see [OpenSentry - LMV](https://github.com/Sbussiso/OpenSentry).

---

## Future Roadmap

### Planned Features
- [ ] Snapshot archive export (ZIP download)
- [ ] Email/webhook notifications on motion detection
- [ ] Custom snapshot schedules (e.g., only during specific hours)
- [ ] Multi-camera support in single instance
- [ ] Snapshot comparison/diff view
- [ ] Mobile-optimized gallery UI
- [ ] Timelapse video generation from snapshots

### Under Consideration
- [ ] Raspberry Pi Camera Module v2/v3 support
- [ ] Hardware-accelerated JPEG encoding (V4L2)
- [ ] WebP format support for smaller file sizes
- [ ] S3/cloud storage integration (optional)
- [ ] MQTT integration for home automation

---

## Contributing

We welcome contributions! Please see [README.md](README.md#-contributing) for details.

---

## Links

- **Homepage**: [https://github.com/Sbussiso/OpenSentry-SMV](https://github.com/Sbussiso/OpenSentry-SMV)
- **Issues**: [https://github.com/Sbussiso/OpenSentry-SMV/issues](https://github.com/Sbussiso/OpenSentry-SMV/issues)
- **Discussions**: [https://github.com/Sbussiso/OpenSentry-SMV/discussions](https://github.com/Sbussiso/OpenSentry-SMV/discussions)
