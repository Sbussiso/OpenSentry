def render_all_feeds_page() -> str:
    return """
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
        <title>OpenSentry - All Feeds</title>
        <style>
            body { font-family: system-ui, Arial, sans-serif; margin: 0; }
            header { padding: 10px 16px; border-bottom: 1px solid #eee; display: flex; gap: 12px; align-items: center; }
            .grid { display: grid; grid-template-columns: repeat(2, 1fr); grid-auto-rows: minmax(240px, 48vh); gap: 8px; padding: 8px; }
            .tile { position: relative; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; background: #000; }
            .tile h3 { position: absolute; top: 6px; left: 8px; margin: 0; padding: 4px 6px; font-size: 12px; color: #fff; background: rgba(0,0,0,0.4); border-radius: 4px; }
            .tile img { width: 100%; height: 100%; object-fit: contain; display: block; background: #000; }
            .links { margin-left: auto; }
            .links a { margin-left: 10px; }
        </style>
    </head>
    <body>
        <header>
            <strong>All Feeds</strong>
            <div class=\"links\"><a href=\"/\">Home</a> · <a href=\"/settings\">Settings</a></div>
        </header>
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
