from helpers.theme import get_css, header_html


def render_all_feeds_page() -> str:
    css = get_css() + """
    .grid { display: grid; grid-template-columns: repeat(2, 1fr); grid-auto-rows: minmax(240px, 48vh); gap: 10px; padding: 10px; }
    .tile { position: relative; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; background: #0e131b; }
    .tile h3 { position: absolute; top: 8px; left: 10px; margin: 0; padding: 4px 8px; font-size: 12px; color: #fff; background: rgba(0,0,0,0.35); border-radius: 6px; }
    .tile video { width: 100%; height: 100%; object-fit: contain; display: block; background: #000; }
    .controls { position:absolute; right: 8px; top: 8px; display:flex; gap:6px; }
    .btn { padding:4px 8px; background: var(--accent); color:#fff; border-radius:6px; font-weight:600; border:0; cursor:pointer; font-size:12px; }
    .btn.secondary { background: transparent; border:1px solid var(--border); color: var(--text); }
    .toolbar { display:flex; gap:8px; padding: 8px 12px; }
    .note { padding: 8px 12px; color: var(--muted); }
    """
    hdr = header_html("All Feeds (HLS)")
    return f"""
    <!DOCTYPE html>
    <html lang=\"en\"> 
    <head>
      <meta charset=\"utf-8\"> 
      <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> 
      <style>{css}</style>
      <script src=\"https://cdn.jsdelivr.net/npm/hls.js@latest\"></script>
    </head>
    <body>
      {hdr}
      <div class=\"toolbar\">
        <span class=\"note\">Use the buttons below to start/stop individual tiles.</span>
      </div>
      <div class=\"grid\">
        <div class=\"tile\">
          <h3>Raw</h3>
          <div class=\"controls\"><button class=\"btn\" data-action=\"play\" data-id=\"raw\">Play</button><button class=\"btn secondary\" data-action=\"stop\" data-id=\"raw\">Stop</button></div>
          <video id=\"raw\" data-src=\"/hls/raw/index.m3u8\" muted playsinline></video>
{{ ... }}
        <div class=\"tile\">
          <h3>Motion</h3>
          <div class=\"controls\"><button class=\"btn\" data-action=\"play\" data-id=\"motion\">Play</button><button class=\"btn secondary\" data-action=\"stop\" data-id=\"motion\">Stop</button></div>
          <video id=\"motion\" data-src=\"/hls/motion/index.m3u8\" muted playsinline></video>
        </div>
        <div class=\"tile\">
          <h3>Objects</h3>
          <div class=\"controls\"><button class=\"btn\" data-action=\"play\" data-id=\"objects\">Play</button><button class=\"btn secondary\" data-action=\"stop\" data-id=\"objects\">Stop</button></div>
          <video id=\"objects\" data-src=\"/hls/objects/index.m3u8\" muted playsinline></video>
        </div>
        <div class=\"tile\">
          <h3>Faces</h3>
          <div class=\"controls\"><button class=\"btn\" data-action=\"play\" data-id=\"faces\">Play</button><button class=\"btn secondary\" data-action=\"stop\" data-id=\"faces\">Stop</button></div>
          <video id=\"faces\" data-src=\"/hls/faces/index.m3u8\" muted playsinline></video>
        </div>
      </div>
      <script>
      (function(){{
        const players = {{}};
        function play(id){{
          const el = document.getElementById(id);
          if (!el) return;
          const src = el.getAttribute('data-src');
          if (!src) return;
          if (window.Hls && window.Hls.isSupported()) {{
            if (players[id]) {{ players[id].destroy(); delete players[id]; }}
            const hls = new Hls({ lowLatencyMode: true, backBufferLength: 30 });
            hls.loadSource(src);
            hls.attachMedia(el);
            players[id] = hls;
          }} else if (el.canPlayType('application/vnd.apple.mpegurl')) {{
            el.src = src;
          }}
          el.play().catch(()=>{{}});
        }}
        function stop(id){{
          const el = document.getElementById(id);
          if (!el) return;
          try {{ el.pause(); }} catch(e){{}}
          try {{ el.removeAttribute('src'); el.load(); }} catch(e){{}}
          if (players[id]) {{ players[id].destroy(); delete players[id]; }}
        }}
        document.addEventListener('click', function(e){{
          const t = e.target;
          if (t && t.dataset && t.dataset.action){{
            const id = t.dataset.id;
            if (t.dataset.action === 'play') play(id);
            if (t.dataset.action === 'stop') stop(id);
          }}
        }});
        document.getElementById('startAll')?.addEventListener('click', function(){{
          const ids = ['raw','motion','faces','objects'];
          let i = 0;
          (function next(){{ if (i>=ids.length) return; play(ids[i++]); setTimeout(next, 500); }})();
        }});
        document.getElementById('stopAll')?.addEventListener('click', function(){{
          ['raw','motion','faces','objects'].forEach(stop);
        }});
      }})();
      </script>
    </body>
    </html>
    """
