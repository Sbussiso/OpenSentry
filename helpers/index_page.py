from helpers.theme import get_css, header_html

def render_index_page() -> str:
    css = get_css() + """
    .wrap { display:flex; align-items:center; justify-content:center; padding:32px 16px; }
    .card { width:100%; max-width:720px; background: var(--surface); border:1px solid var(--border); border-radius:12px; padding:20px 22px; box-shadow:0 6px 30px rgba(0,0,0,0.35); }
    h1 { margin:0 0 6px; font-size:22px; }
    p.lead { margin:0 0 16px; color: var(--muted); }
    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:12px; }
    .tile { border:1px solid var(--border); border-radius:8px; padding:14px; background:#0e131b; }
    .tile h3 { margin:0 0 8px; font-size:16px; }
    .btns a { display:inline-block; margin-right:10px; margin-top:8px; padding:8px 12px; border-radius:8px; background:var(--accent); color:#fff; font-weight:600; }
    .btns a.secondary { background: transparent; border:1px solid var(--border); color: var(--text); }
    """
    hdr = header_html("OpenSentry")
    return f"""
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
        <title>OpenSentry</title>
        <style>{css}</style>
    </head>
    <body>
        {hdr}
        <div class=\"wrap\"> 
            <div class=\"card\"> 
                <h1>Streams</h1>
                <p class=\"lead\">Open a stream in a new tab.</p>
                <div class=\"grid\"> 
                    <div class=\"tile\"> 
                        <h3>Raw Feed</h3>
                        <div class=\"btns\"><a href=\"/video_feed\" target=\"_blank\" rel=\"noopener\">Open</a></div>
                    </div>
                    <div class=\"tile\"> 
                        <h3>Motion Detection</h3>
                        <div class=\"btns\"><a href=\"/video_feed_motion\" target=\"_blank\" rel=\"noopener\">Open</a></div>
                    </div>
                    <div class=\"tile\"> 
                        <h3>Object Detection</h3>
                        <div class=\"btns\"><a href=\"/video_feed_objects\" target=\"_blank\" rel=\"noopener\">Open</a></div>
                    </div>
                    <div class=\"tile\"> 
                        <h3>Face Detection</h3>
                        <div class=\"btns\"><a href=\"/video_feed_faces\" target=\"_blank\" rel=\"noopener\">Open</a></div>
                    </div>
                </div>
                <div style=\"margin-top:12px;\"><a class=\"secondary btns a\" href=\"/all_feeds\">View 2x2 Grid</a></div>
            </div>
        </div>
    </body>
    </html>
    """
