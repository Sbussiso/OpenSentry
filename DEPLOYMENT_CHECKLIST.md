# Deployment Checklist for OpenSentry - SMV

This checklist ensures you have a secure, production-ready deployment.

## Pre-Deployment

### Security
- [ ] Change `OPENSENTRY_USER` from default `admin`
- [ ] Change `OPENSENTRY_PASS` from default `admin` 
- [ ] Generate random `OPENSENTRY_SECRET` (64+ characters)
- [ ] Review and update OAuth2 settings if using OAuth2 mode
- [ ] Remove or secure any test/development credentials

### Configuration
- [ ] Review `OPENSENTRY_SNAPSHOT_INTERVAL` for your use case (5-60 seconds)
- [ ] Adjust `OPENSENTRY_JPEG_QUALITY` based on storage/bandwidth (30-95)
- [ ] Set appropriate snapshot retention (`retention_count` and `retention_days`)
- [ ] Configure camera resolution if needed (`OPENSENTRY_CAMERA_WIDTH`/`HEIGHT`)
- [ ] Set `OPENSENTRY_DEVICE_NAME` for easy identification
- [ ] Configure `OPENSENTRY_PORT` if 5000 is already in use

### Hardware
- [ ] Verify camera is accessible at `/dev/video0` (or adjust `devices` in compose.yaml)
- [ ] Test camera with `v4l2-ctl --list-devices`
- [ ] Ensure adequate storage for snapshots (estimate: ~2MB per 100 snapshots at 320x240)
- [ ] For Pi Zero W: Consider increasing interval to 15-20 seconds

## Deployment

### Docker Compose
```bash
# Clone repository
git clone https://github.com/Sbussiso/OpenSentry-SMV.git
cd OpenSentry-SMV

# Build and start
docker compose up -d --build

# Verify startup
docker logs -f opensentry-smv

# Check health
curl http://localhost:5000/health
```

### Environment File
Create `.env` file for production secrets:
```bash
OPENSENTRY_USER=your-username
OPENSENTRY_PASS=your-secure-password
OPENSENTRY_SECRET=your-64-char-random-secret
OPENSENTRY_PORT=5000
```

Update compose.yaml to use `.env`:
```yaml
environment:
  - OPENSENTRY_USER=${OPENSENTRY_USER}
  - OPENSENTRY_PASS=${OPENSENTRY_PASS}
  - OPENSENTRY_SECRET=${OPENSENTRY_SECRET}
```

## Post-Deployment

### Verification
- [ ] Access web UI at `http://your-device:5000`
- [ ] Login with configured credentials
- [ ] Verify snapshot capture is working (check gallery)
- [ ] Test motion detection overlay (wave hand in front of camera)
- [ ] Verify automatic retention cleanup (check logs after 10+ captures)
- [ ] Test settings page and parameter adjustments
- [ ] Verify mDNS discovery (if enabled): `avahi-browse -r _opensentry._tcp`

### Monitoring
- [ ] Set up log rotation for Docker logs
- [ ] Monitor disk usage for `/app/snapshots`
- [ ] Check CPU usage: should be 10-30% on Pi Zero W
- [ ] Verify memory usage: should be ~60MB on Pi Zero W
- [ ] Set up alerts for camera failures (optional)

### Backup
- [ ] Backup `config.json` regularly
- [ ] Consider backing up snapshots directory (or use external storage)
- [ ] Document your OAuth2 configuration (if used)

## Optional: HTTPS with Reverse Proxy

### Nginx Example
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

- [ ] Install nginx/traefik/caddy
- [ ] Obtain SSL certificate (Let's Encrypt recommended)
- [ ] Configure reverse proxy
- [ ] Update OAuth2 redirect URIs to use HTTPS URLs
- [ ] Test HTTPS access

## Production Hardening

### Network Security
- [ ] Disable mDNS in production: `OPENSENTRY_MDNS_DISABLE=1`
- [ ] Use firewall rules to restrict access to trusted networks
- [ ] Consider VPN access for remote monitoring
- [ ] Enable OAuth2 for centralized authentication

### Docker Security
- [ ] Run container as non-root user (if camera permissions allow)
- [ ] Use Docker secrets for sensitive data
- [ ] Regularly update base images and dependencies
- [ ] Scan images for vulnerabilities: `docker scan opensentry-smv:latest`

### Maintenance
- [ ] Schedule regular dependency updates: `uv sync --upgrade`
- [ ] Monitor for security advisories
- [ ] Review logs weekly for unauthorized access attempts
- [ ] Test snapshot restoration procedures
- [ ] Document any custom configurations

## Troubleshooting

### Camera Not Working
```bash
# Check device permissions
ls -la /dev/video0

# Test camera directly
v4l2-ctl -d /dev/video0 --list-formats-ext

# Check container logs
docker logs opensentry-smv | grep -i camera
```

### High CPU Usage on Pi Zero W
- Increase `OPENSENTRY_SNAPSHOT_INTERVAL` to 15-20 seconds
- Lower `OPENSENTRY_JPEG_QUALITY` to 60
- Reduce camera resolution in environment variables
- Disable motion detection overlay: set `snapshot_motion_detection: false` in settings

### Disk Space Issues
```bash
# Check snapshot directory size
du -sh /path/to/snapshots

# Adjust retention in settings or config.json
# Lower retention_count (e.g., 50 instead of 100)
# Lower retention_days (e.g., 3 instead of 7)
```

### OAuth2 Issues
- Verify OAuth2 server is accessible: `curl http://oauth2-server/.well-known/openid-configuration`
- Check redirect URIs match exactly (including protocol, host, port, path)
- Use fallback URL: `http://your-opensentry:5000/oauth2/fallback`
- Review OAuth2 server logs for detailed error messages

## Support

- **Issues**: https://github.com/Sbussiso/OpenSentry-SMV/issues
- **Discussions**: https://github.com/Sbussiso/OpenSentry-SMV/discussions
- **Documentation**: See `docs/` folder

---

**Version**: 1.0.0  
**Last Updated**: 2025-10-25
