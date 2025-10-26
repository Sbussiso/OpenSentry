from helpers.theme import get_css, header_html

def render_snapshot_page() -> str:
    """Render the snapshot gallery page for snapshot-only mode."""
    css = get_css() + """
    .wrap { display:flex; align-items:flex-start; justify-content:center; padding:32px 16px; }
    .container { width:100%; max-width:1200px; }
    .card { background: var(--surface); border:1px solid var(--border); border-radius:12px; padding:20px 22px; box-shadow:0 6px 30px rgba(0,0,0,0.35); margin-bottom:20px; }
    h1 { margin:0 0 8px; font-size:22px; }
    .subtitle { color: var(--muted); font-size:14px; margin-bottom:16px; }
    .latest-container { width:100%; border-radius:8px; overflow:hidden; border:1px solid var(--border); background:#000; margin-bottom:16px; position:relative; }
    .latest-container img { width:100%; height:auto; display:block; }
    .refresh-overlay { position:absolute; top:10px; right:10px; background:rgba(0,0,0,0.7); color:#fff; padding:6px 12px; border-radius:6px; font-size:12px; }
    .stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-bottom:16px; }
    .stat-box { background: var(--background); border:1px solid var(--border); border-radius:8px; padding:12px; text-align:center; }
    .stat-value { font-size:24px; font-weight:700; color: var(--accent); }
    .stat-label { font-size:12px; color: var(--muted); margin-top:4px; }
    .controls { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }
    .btn { background: var(--accent); color:#fff; border:0; padding:10px 20px; border-radius:8px; font-weight:600; cursor:pointer; font-size:14px; }
    .btn:hover { filter: brightness(1.1); }
    .btn.secondary { background: var(--button-secondary); }
    .btn:disabled { opacity:0.5; cursor:not-allowed; }
    .gallery { display:grid; grid-template-columns:repeat(auto-fill, minmax(250px, 1fr)); gap:16px; }
    .gallery-item { background: var(--background); border:1px solid var(--border); border-radius:8px; overflow:hidden; cursor:pointer; transition: transform 0.2s, box-shadow 0.2s; }
    .gallery-item:hover { transform: translateY(-2px); box-shadow:0 8px 20px rgba(0,0,0,0.4); }
    .gallery-img { width:100%; aspect-ratio:4/3; object-fit:cover; background:#000; }
    .gallery-info { padding:12px; }
    .gallery-title { font-size:13px; font-weight:600; margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .gallery-meta { font-size:11px; color: var(--muted); display:flex; justify-content:space-between; align-items:center; }
    .badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:10px; font-weight:700; text-transform:uppercase; }
    .badge.motion { background: #ef4444; color:#fff; }
    .badge.snapshot { background: #6b7280; color:#fff; }
    .modal { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.9); z-index:1000; align-items:center; justify-content:center; padding:20px; }
    .modal.active { display:flex; }
    .modal-content { max-width:90vw; max-height:90vh; position:relative; }
    .modal-img { max-width:100%; max-height:80vh; border-radius:8px; }
    .modal-close { position:absolute; top:-40px; right:0; background:var(--accent); color:#fff; border:0; width:36px; height:36px; border-radius:50%; cursor:pointer; font-size:20px; }
    .modal-info { margin-top:12px; background: var(--surface); padding:12px; border-radius:8px; }
    .empty-state { text-align:center; padding:40px 20px; color: var(--muted); }
    .empty-state-icon { font-size:48px; margin-bottom:16px; opacity:0.5; }
    """
    hdr = header_html("OpenSentry - Snapshot Gallery")
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>OpenSentry - Snapshot Gallery</title>
        <style>{css}</style>
    </head>
    <body>
        {hdr}
        <div class="wrap">
            <div class="container">
                <!-- Latest Snapshot Card -->
                <div class="card">
                    <h1>Latest Snapshot</h1>
                    <div class="subtitle">Live view refreshes every 10 seconds</div>
                    <div class="latest-container">
                        <img id="latest-img" src="/api/snapshots/latest" alt="Latest Snapshot" />
                        <div class="refresh-overlay" id="refresh-status">Loading...</div>
                    </div>
                    <div class="stats">
                        <div class="stat-box">
                            <div class="stat-value" id="total-count">-</div>
                            <div class="stat-label">Total Snapshots</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="motion-count">-</div>
                            <div class="stat-label">Motion Detected</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="snapshot-interval">-</div>
                            <div class="stat-label">Capture Interval</div>
                        </div>
                    </div>
                    <div class="controls">
                        <button class="btn" onclick="refreshGallery()">Refresh Gallery</button>
                        <button class="btn secondary" onclick="downloadLatest()">Download Latest</button>
                    </div>
                </div>

                <!-- Gallery Card -->
                <div class="card">
                    <h1>Snapshot History</h1>
                    <div class="subtitle" id="gallery-subtitle">Recent snapshots from this device</div>
                    <div id="gallery" class="gallery">
                        <div class="empty-state">
                            <div class="empty-state-icon">📷</div>
                            <div>Loading snapshots...</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Modal for full-size view -->
        <div id="modal" class="modal" onclick="closeModal(event)">
            <div class="modal-content">
                <button class="modal-close" onclick="closeModal(event)">×</button>
                <img id="modal-img" class="modal-img" src="" alt="Full Size" />
                <div class="modal-info">
                    <div id="modal-details"></div>
                </div>
            </div>
        </div>

        <script>
        let refreshInterval = null;
        let lastRefreshTime = 0;

        // Auto-refresh latest snapshot every 10 seconds
        function startAutoRefresh() {{
            refreshLatestImage();
            if (refreshInterval) clearInterval(refreshInterval);
            refreshInterval = setInterval(refreshLatestImage, 10000);
        }}

        function refreshLatestImage() {{
            const img = document.getElementById('latest-img');
            const status = document.getElementById('refresh-status');

            // Add timestamp to prevent caching
            const timestamp = new Date().getTime();
            img.src = '/api/snapshots/latest?t=' + timestamp;

            const now = new Date();
            status.textContent = 'Updated ' + now.toLocaleTimeString();
            lastRefreshTime = timestamp;
        }}

        // Load snapshot gallery
        async function loadGallery() {{
            try {{
                const response = await fetch('/api/snapshots/list');
                if (!response.ok) throw new Error('Failed to load snapshots');

                const data = await response.json();
                renderGallery(data);
            }} catch (err) {{
                console.error('Gallery load error:', err);
                document.getElementById('gallery').innerHTML =
                    '<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>Failed to load snapshots</div></div>';
            }}
        }}

        function renderGallery(data) {{
            const gallery = document.getElementById('gallery');
            const totalCount = document.getElementById('total-count');
            const motionCount = document.getElementById('motion-count');

            totalCount.textContent = data.count || 0;
            const motionSnaps = data.snapshots.filter(s => s.motion_detected).length;
            motionCount.textContent = motionSnaps;

            if (data.count === 0) {{
                gallery.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📷</div><div>No snapshots yet. Waiting for captures...</div></div>';
                return;
            }}

            gallery.innerHTML = data.snapshots.map(snap => {{
                const date = new Date(snap.timestamp * 1000);
                const dateStr = date.toLocaleDateString();
                const timeStr = date.toLocaleTimeString();
                const badge = snap.motion_detected ?
                    `<span class="badge motion">Motion ${{snap.motion_area}}px</span>` :
                    '<span class="badge snapshot">Snapshot</span>';

                return `
                    <div class="gallery-item" onclick='openModal(${{JSON.stringify(snap)}})'>
                        <img class="gallery-img" src="${{snap.url}}" alt="${{snap.filename}}" loading="lazy" />
                        <div class="gallery-info">
                            <div class="gallery-title">${{snap.filename}}</div>
                            <div class="gallery-meta">
                                <span>${{timeStr}}</span>
                                ${{badge}}
                            </div>
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        function openModal(snap) {{
            const modal = document.getElementById('modal');
            const img = document.getElementById('modal-img');
            const details = document.getElementById('modal-details');

            img.src = snap.url;

            const date = new Date(snap.timestamp * 1000);
            const sizeKB = (snap.size / 1024).toFixed(1);
            details.innerHTML = `
                <strong>${{snap.filename}}</strong><br>
                Time: ${{date.toLocaleString()}}<br>
                Size: ${{sizeKB}} KB<br>
                ${{snap.motion_detected ? `Motion Area: ${{snap.motion_area}} pixels` : 'No motion detected'}}
            `;

            modal.classList.add('active');
        }}

        function closeModal(event) {{
            if (event.target.id === 'modal' || event.target.classList.contains('modal-close')) {{
                document.getElementById('modal').classList.remove('active');
            }}
        }}

        async function downloadLatest() {{
            try {{
                const response = await fetch('/api/snapshot');
                if (!response.ok) throw new Error('Failed to download');

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'opensentry-snapshot-' + new Date().toISOString().replace(/[:.]/g, '-') + '.jpg';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            }} catch (err) {{
                console.error('Download error:', err);
                alert('Failed to download snapshot');
            }}
        }}

        function refreshGallery() {{
            loadGallery();
            refreshLatestImage();
        }}

        // Initialize on page load
        document.addEventListener('DOMContentLoaded', () => {{
            startAutoRefresh();
            loadGallery();

            // Set snapshot interval stat (get from config or default to 10s)
            document.getElementById('snapshot-interval').textContent = '10s';
        }});

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {{
            if (refreshInterval) clearInterval(refreshInterval);
        }});
        </script>
    </body>
    </html>
    """
