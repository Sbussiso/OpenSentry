from helpers.theme import get_css, header_html


def render_all_feeds_page() -> str:
    css = get_css() + """
    .grid { display: grid; grid-template-columns: repeat(2, 1fr); grid-auto-rows: minmax(240px, 48vh); gap: 10px; padding: 10px; }
    .tile { position: relative; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; background: #0e131b; }
    .tile h3 { position: absolute; top: 8px; left: 10px; margin: 0; padding: 4px 8px; font-size: 12px; color: #fff; background: rgba(0,0,0,0.35); border-radius: 6px; }
    .tile img { width: 100%; height: 100%; object-fit: contain; display: block; background: #000; }
    """
    hdr = header_html("All Feeds")
    return f"""
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
        <title>OpenSentry - All Feeds</title>
        <style>{css}</style>
    </head>
    <body>
        {hdr}
        <div class=\"grid\">
            <div class=\"tile\">
                <h3>Raw</h3>
                <img src=\"/video_feed\" alt=\"Raw feed\" />
            </div>
            <div class=\"tile\">
                <h3>Motion</h3>
                <img src=\"/video_feed_motion\" alt=\"Motion detection feed\" />
            </div>
            <div class=\"tile\">
                <h3>Objects</h3>
                <img src=\"/video_feed_objects\" alt=\"Object detection feed\" />
            </div>
            <div class=\"tile\">
                <h3>Faces</h3>
                <img src=\"/video_feed_faces\" alt=\"Face detection feed\" />
            </div>
        </div>
    </body>
    </html>
    """
