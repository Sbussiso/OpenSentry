from helpers.theme import get_css, header_html

def render_index_page() -> str:
    css = get_css() + """
    .wrap { display:flex; align-items:center; justify-content:center; padding:32px 16px; }
    .card { width:100%; max-width:960px; background: var(--surface); border:1px solid var(--border); border-radius:12px; padding:20px 22px; box-shadow:0 6px 30px rgba(0,0,0,0.35); }
    h1 { margin:0 0 16px; font-size:22px; text-align: center; }
    .video-container { width:100%; border-radius:8px; overflow:hidden; border:1px solid var(--border); background:#000; margin-bottom:16px; }
    .video-container img { width:100%; height:auto; display:block; }
    .controls { display:flex; justify-content:center; gap:12px; }
    .btn { background: var(--accent); color:#fff; border:0; padding:10px 20px; border-radius:8px; font-weight:600; cursor:pointer; font-size:14px; }
    .btn:hover { filter: brightness(1.1); }
    .btn:disabled { opacity:0.5; cursor:not-allowed; }
    """
    hdr = header_html("OpenSentry - Motion Detection Camera")
    return f"""
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
        <title>OpenSentry - Motion Detection Camera</title>
        <style>{css}</style>
    </head>
    <body>
        {hdr}
        <div class=\"wrap\">
            <div class=\"card\">
                <h1>OpenSentry Feed</h1>
                <div class=\"video-container\">
                    <img src=\"/video_feed_motion\" alt=\"Motion Detection Feed\" />
                </div>
                <div class=\"controls\">
                    <button class=\"btn\" id=\"snapshot-btn\" onclick=\"captureSnapshot()\">Take Snapshot</button>
                </div>
            </div>
        </div>
        <script>
        async function captureSnapshot() {{
            const btn = document.getElementById('snapshot-btn');
            btn.disabled = true;
            btn.textContent = 'Capturing...';

            try {{
                const response = await fetch('/api/snapshot');
                if (!response.ok) {{
                    throw new Error('Failed to capture snapshot');
                }}

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'opensentry-snapshot-' + new Date().toISOString().replace(/[:.]/g, '-') + '.jpg';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                btn.textContent = 'Snapshot Saved!';
                setTimeout(() => {{
                    btn.textContent = 'Take Snapshot';
                    btn.disabled = false;
                }}, 2000);
            }} catch (err) {{
                console.error('Snapshot error:', err);
                btn.textContent = 'Error - Try Again';
                setTimeout(() => {{
                    btn.textContent = 'Take Snapshot';
                    btn.disabled = false;
                }}, 2000);
            }}
        }}
        </script>
    </body>
    </html>
    """
