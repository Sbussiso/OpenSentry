def render_index_page() -> str:
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        
        <title>OpenSentry</title>
    </head>
    <body>
    <center>
        <container style="display:inline-block;border:2px solid #ccc;border-radius:8px;padding:16px 20px;margin-top:20px;">
            <h1>OpenSentry</h1>
            <p>Open a stream in a new tab:</p>
            <ul>
                <p><a href="/video_feed" target="_blank" rel="noopener">Raw Feed (direct)</a></p>
                <p><a href="/video_feed_motion" target="_blank" rel="noopener">Motion Detection Feed (direct)</a></p>
                <p><a href="/video_feed_objects" target="_blank" rel="noopener">Object Detection Feed (direct)</a></p>
                <p><a href="/video_feed_faces" target="_blank" rel="noopener">Face Detection Feed (direct)</a></p>
            </ul>
            <p><a href="/all_feeds">All Feeds (2x2 grid)</a> · <a href="/settings">Settings</a></p>
        </container>
    </center>
    </body>
    </html>
    """
