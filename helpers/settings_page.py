from typing import Set, List
from helpers.theme import get_css, header_html


def render_settings_page(
    *,
    names: List[str],
    select_all_flag: bool,
    selected: Set[str],
    m_thresh: int,
    m_min_area: int,
    m_kernel: int,
    m_iters: int,
    m_pad: int,
    f_archive: bool,
    f_min_dur: int,
    f_dir: str,
    f_dedup: bool,
    f_dd_th: int,
    f_cool: int,
    f_method: str,
    f_embed_th: float,
    raw_ok: bool,
    motion_ok: bool,
    objects_ok: bool,
    faces_ok: bool,
    face_recognition_available: bool,
    unknowns: list = [],
    device_id: str = '',
    port: int = 5000,
    mdns_enabled: bool = True,
    app_version: str = '',
    auth_mode: str = 'local',
    oauth2_base_url: str = '',
    oauth2_client_id: str = '',
    oauth2_client_secret: str = '',
    oauth2_scope: str = 'openid profile email offline_access',
    # Camera/stream tuning
    cam_width: int = 0,
    cam_height: int = 0,
    cam_fps: int = 15,
    cam_mjpeg: bool = True,
    out_max_width: int = 960,
    jpeg_quality: int = 75,
    raw_fps: int = 15,
) -> str:
    options_html = ''
    if names:
        for n in names:
            checked = 'checked' if (n in selected and not select_all_flag) else ''
            options_html += f'<label><input type="checkbox" name="classes" value="{n}" {checked}> {n}</label>'
    else:
        options_html = '<p><em>YOLO classes unavailable. Install ultralytics and restart to configure.</em></p>'

    select_all_checked = 'checked' if select_all_flag else ''
    archive_unknown_checked = 'checked' if f_archive else ''
    face_dedup_checked = 'checked' if f_dedup else ''
    method_embed_checked = 'checked' if f_method == 'embedding' else ''
    method_phash_checked = 'checked' if f_method == 'phash' else ''

    # OAuth2 settings
    auth_mode_local_checked = 'checked' if auth_mode == 'local' else ''
    auth_mode_oauth2_checked = 'checked' if auth_mode == 'oauth2' else ''

    raw_class = 'ok' if raw_ok else 'down'
    raw_text = 'Active' if raw_ok else 'Down'
    motion_class = 'ok' if motion_ok else 'down'
    motion_text = 'Active' if motion_ok else 'Down'
    objects_class = 'ok' if objects_ok else 'down'
    objects_text = 'Active' if objects_ok else 'Down'
    faces_class = 'ok' if faces_ok else 'down'
    faces_text = 'Active' if faces_ok else 'Down'

    face_recog_label = 'Available' if face_recognition_available else 'Unavailable'

    # Build unknowns management HTML
    unknowns_html = ''
    if unknowns:
        cards = []
        for u in unknowns:
            uid = u.get('uid', '')
            ts = u.get('ts', '')
            img_url = u.get('img_url', '')
            cards.append(f"""
            <div class=\"card\">
              <div class=\"img\"><img src=\"{img_url}\" alt=\"{uid}\"/></div>
              <div class=\"meta\"><div><strong>{uid}</strong></div><div>{ts}</div></div>
              <form method=\"post\" action=\"/settings\" class=\"actions\">
                <input type=\"hidden\" name=\"uid\" value=\"{uid}\"> 
                <input type=\"text\" name=\"name\" placeholder=\"Name\" />
                <button type=\"submit\" name=\"action\" value=\"promote_unknown\">Promote to Known</button>
                <button type=\"submit\" name=\"action\" value=\"delete_unknown\" onclick=\"return confirm('Delete this snapshot and entry?');\">Delete</button>
              </form>
            </div>
            """)
        unknowns_html = f"""
        <fieldset>
          <legend>Manage Unknown IDs</legend>
          <div class=\"unknowns-grid\">{''.join(cards)}</div>
          <p><small>Promote a UID to a known name. Promoting moves the embedding to the Known list so future matches display the name.</small></p>
        </fieldset>
        """

    css = get_css() + """
            .form-wrap { max-width: 1040px; margin: 0 auto; padding: 16px; }
            fieldset { border: 1px solid var(--border); background: var(--surface); border-radius: 10px; padding: 14px; margin-top: 14px; }
            legend { color: var(--muted); }
            .options-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px 16px; align-items: center; }
            .options-grid label { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
            .status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px 14px; align-items: center; }
            .status-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background:#0e131b; }
            .pill { padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.9em; border: 1px solid transparent; }
            .pill.ok { background: rgba(22,163,74,0.15); color: #86efac; border-color: rgba(22,163,74,0.35); }
            .pill.down { background: rgba(239,68,68,0.15); color: #fecaca; border-color: rgba(239,68,68,0.35); }
            .md-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px 18px; align-items: start; }
            .md-grid .control { display: flex; flex-direction: column; gap: 6px; }
            .md-grid .control .control-title { display: flex; gap: 8px; align-items: baseline; justify-content: space-between; color: var(--muted); }
            .md-grid .control output { font-variant-numeric: tabular-nums; min-width: 3ch; text-align: right; color: var(--text); }
            input[type=range] { width: 100%; accent-color: var(--accent); }
            input[type=text] { background:#0e131b; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; }
            input[type=checkbox], input[type=radio] { accent-color: var(--accent); }
            button { background: var(--accent); color:#fff; border:0; padding:8px 12px; border-radius:8px; font-weight:600; cursor:pointer; }
            button:hover { filter: brightness(1.05); }
            .unknowns-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap:12px; }
            .unknowns-grid .card { border:1px solid var(--border); border-radius:10px; overflow:hidden; display:flex; flex-direction:column; background:#0e131b; }
            .unknowns-grid .img img { width:100%; display:block; }
            .unknowns-grid .meta { padding:8px; display:flex; justify-content:space-between; align-items:center; color:var(--muted); }
            .unknowns-grid .actions { display:flex; gap:8px; padding:8px; align-items:center; border-top:1px solid var(--border); flex-wrap: wrap; }
            .unknowns-grid .actions input[type=text] { flex: 1 1 240px; min-width: 240px; padding:8px; font-size: 14px; }
            .auth-mode-options { display:flex; gap:16px; margin:12px 0; }
            .oauth2-fields { display:grid; gap:12px; margin-top:12px; }
            .oauth2-fields label { display:flex; flex-direction:column; gap:4px; }
            .oauth2-fields input[type=text] { width:100%; }
            #oauth2_test_btn { margin-top:8px; }
            #oauth2_test_result { margin-top:8px; padding:8px; border-radius:6px; display:none; }
            #oauth2_test_result.success { background:rgba(22,163,74,0.15); color:#86efac; border:1px solid rgba(22,163,74,0.35); }
            #oauth2_test_result.error { background:rgba(239,68,68,0.15); color:#fecaca; border:1px solid rgba(239,68,68,0.35); }
    """
    hdr = header_html('Settings')

    return f"""
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\">
        <title>OpenSentry Settings</title>
        <style>{css}</style>
    </head>
    <body>
        {hdr}
        <div class=\"form-wrap\">
            <fieldset>
                <legend>Device info</legend>
                <div class=\"status-grid\">
                    <div class=\"status-item\"><span>Device ID</span><span><code>{device_id}</code></span></div>
                    <div class=\"status-item\"><span>Version</span><span><code>{app_version}</code></span></div>
                    <div class=\"status-item\"><span>HTTP Port</span><span><code>{port}</code></span></div>
                    <div class=\"status-item\"><span>mDNS</span><span class=\"pill {('ok' if mdns_enabled else 'down')}\">{('ENABLED' if mdns_enabled else 'DISABLED')}</span></div>
                </div>
            </fieldset>
            <fieldset>
                <legend>Diagnostics</legend>
                <form method="get" action="/logs/download" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                    <label for="n" style="color: var(--muted);">Lines (optional)</label>
                    <input type="number" name="n" min="0" placeholder="All" style="width:120px; background:#0e131b; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:6px 8px;">
                    <button type="submit">Download Server Logs</button>
                </form>
                <p><small>Downloads recent in-memory logs as a text file. Leave lines empty to include all buffered logs.</small></p>
            </fieldset>
            <form method=\"post\" action=\"/settings\">
                <input type=\"hidden\" name=\"action\" value=\"update_auth\">
                <fieldset>
                    <legend>Authentication Settings</legend>
                    <div class=\"auth-mode-options\">
                        <label><input type=\"radio\" name=\"auth_mode\" value=\"local\" {auth_mode_local_checked}> Local Authentication (username/password)</label>
                        <label><input type=\"radio\" name=\"auth_mode\" value=\"oauth2\" {auth_mode_oauth2_checked}> OAuth2 Authentication</label>
                    </div>
                    <div id=\"oauth2_settings\" style=\"display:{'block' if auth_mode == 'oauth2' else 'none'};\">
                        <div class=\"oauth2-fields\">
                            <label>
                                <span>OAuth2 Server Base URL</span>
                                <input type=\"text\" name=\"oauth2_base_url\" value=\"{oauth2_base_url}\" placeholder=\"http://127.0.0.1:8000\">
                            </label>
                            <label>
                                <span>Client ID</span>
                                <input type=\"text\" name=\"oauth2_client_id\" value=\"{oauth2_client_id}\" placeholder=\"opensentry-device\">
                            </label>
                            <label>
                                <span>Client Secret (optional, for confidential clients)</span>
                                <input type=\"text\" name=\"oauth2_client_secret\" value=\"{oauth2_client_secret}\" placeholder=\"\">
                            </label>
                            <label>
                                <span>Scope</span>
                                <input type=\"text\" name=\"oauth2_scope\" value=\"{oauth2_scope}\" placeholder=\"openid profile email offline_access\">
                            </label>
                        </div>
                        <button type=\"button\" id=\"oauth2_test_btn\" class=\"btn\">Test OAuth2 Connection</button>
                        <div id=\"oauth2_test_result\"></div>
                    </div>
                    <p><small><strong>Warning:</strong> Switching to OAuth2 will require you to authenticate via the configured OAuth2 server. Make sure the server is accessible and properly configured before saving.</small></p>
                </fieldset>
                <p><button type=\"submit\">Save Authentication Settings</button></p>
            </form>
            <fieldset>
                <legend>Camera route status</legend>
                <div class=\"status-grid\">
                    <div class=\"status-item\"><span>Raw feed</span><span class=\"pill {raw_class}\">{raw_text}</span></div>
                    <div class=\"status-item\"><span>Motion detection</span><span class=\"pill {motion_class}\">{motion_text}</span></div>
                    <div class=\"status-item\"><span>Object detection</span><span class=\"pill {objects_class}\">{objects_text}</span></div>
                    <div class=\"status-item\"><span>Face detection</span><span class=\"pill {faces_class}\">{faces_text}</span></div>
                </div>
            </fieldset>
            <form method=\"post\" action=\"/settings\"> 
                <p><label><input type=\"checkbox\" name=\"select_all\" value=\"1\" {select_all_checked}> Detect all classes</label></p>
                <fieldset>
                    <legend>Camera &amp; Stream</legend>
                    <div class=\"md-grid\">
                        <label class=\"control\">
                            <span class=\"control-title\">Camera width (px)</span>
                            <input type=\"number\" name=\"cam_width\" min=\"0\" step=\"1\" value=\"{cam_width}\"> 
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Camera height (px)</span>
                            <input type=\"number\" name=\"cam_height\" min=\"0\" step=\"1\" value=\"{cam_height}\"> 
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Camera FPS: <output id=\"cam_fps_out\">{cam_fps}</output></span>
                            <input type=\"range\" name=\"cam_fps\" min=\"5\" max=\"60\" step=\"1\" value=\"{cam_fps}\" oninput=\"document.getElementById('cam_fps_out').textContent=this.value\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">MJPEG</span>
                            <label><input type=\"checkbox\" name=\"cam_mjpeg\" { 'checked' if cam_mjpeg else '' }> Enable MJPEG</label>
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">JPEG quality: <output id=\"stream_jpeg_quality_out\">{jpeg_quality}</output></span>
                            <input type=\"range\" name=\"stream_jpeg_quality\" min=\"30\" max=\"95\" step=\"1\" value=\"{jpeg_quality}\" oninput=\"document.getElementById('stream_jpeg_quality_out').textContent=this.value\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Stream max width (px)</span>
                            <input type=\"number\" name=\"stream_max_width\" min=\"320\" step=\"10\" value=\"{out_max_width}\"> 
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Stream FPS: <output id=\"stream_raw_fps_out\">{raw_fps}</output></span>
                            <input type=\"range\" name=\"stream_raw_fps\" min=\"5\" max=\"30\" step=\"1\" value=\"{raw_fps}\" oninput=\"document.getElementById('stream_raw_fps_out').textContent=this.value\">
                        </label>
                    </div>
                    <p><small>Leave width/height 0 to use device defaults. Lower dimensions, quality, and FPS reduce CPU and latency.</small></p>
                </fieldset>
                <fieldset>
                    <legend>Select classes (if not detecting all):</legend>
                    <div class=\"options-grid\">{options_html}</div>
                </fieldset>
                <fieldset>
                    <legend>Face detection</legend>
                    <p>
                        <label><input type=\"checkbox\" name=\"face_archive_unknown\" value=\"1\" {archive_unknown_checked}> Archive unknown faces</label>
                    </p>
                    <p><small>When enabled, if a face stays visible for at least {f_min_dur}s, a cropped snapshot is saved to <code>{f_dir}</code>.</small></p>
                    <p><small>Embedding dedup requires <code>face_recognition</code>: {face_recog_label}.</small></p>
                    <div class=\"md-grid\"> 
                        <label class=\"control\">
                            <span class=\"control-title\">Dedup method</span>
                            <label><input type=\"radio\" name=\"face_dedup_method\" value=\"embedding\" {method_embed_checked}> Embedding</label>
                            <label><input type=\"radio\" name=\"face_dedup_method\" value=\"phash\" {method_phash_checked}> pHash</label>
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Min duration (sec): <output id=\"face_min_duration_sec_out\">{f_min_dur}</output></span>
                            <input type=\"range\" name=\"face_min_duration_sec\" min=\"5\" max=\"60\" step=\"1\" value=\"{f_min_dur}\" oninput=\"document.getElementById('face_min_duration_sec_out').textContent=this.value\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Dedup unknown faces: <output id=\"face_dedup_enabled_out\">{ 'ON' if f_dedup else 'OFF' }</output></span>
                            <input type=\"checkbox\" name=\"face_dedup_enabled\" {face_dedup_checked} onchange=\"document.getElementById('face_dedup_enabled_out').textContent=this.checked?'ON':'OFF'\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Dedup threshold (Hamming): <output id=\"face_dedup_threshold_out\">{f_dd_th}</output></span>
                            <input type=\"range\" name=\"face_dedup_threshold\" min=\"0\" max=\"32\" step=\"1\" value=\"{f_dd_th}\" oninput=\"document.getElementById('face_dedup_threshold_out').textContent=this.value\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Embedding threshold: <output id=\"face_embedding_threshold_out\">{f_embed_th}</output></span>
                            <input type=\"range\" name=\"face_embedding_threshold\" min=\"0.3\" max=\"1.2\" step=\"0.01\" value=\"{f_embed_th}\" oninput=\"document.getElementById('face_embedding_threshold_out').textContent=this.value\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Cooldown (minutes): <output id=\"face_cooldown_minutes_out\">{f_cool}</output></span>
                            <input type=\"range\" name=\"face_cooldown_minutes\" min=\"0\" max=\"180\" step=\"5\" value=\"{f_cool}\" oninput=\"document.getElementById('face_cooldown_minutes_out').textContent=this.value\">
                        </label>
                    </div>
                </fieldset>
                <fieldset>
                    <legend>Motion detection sensitivity</legend>
                    <div class=\"md-grid\">
                        <label class=\"control\">
                            <span class=\"control-title\">Pixel threshold: <output id=\"md_threshold_out\">{m_thresh}</output></span>
                            <input type=\"range\" name=\"md_threshold\" min=\"0\" max=\"255\" step=\"1\" value=\"{m_thresh}\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Min area (px): <output id=\"md_min_area_out\">{m_min_area}</output></span>
                            <input type=\"range\" name=\"md_min_area\" min=\"0\" max=\"50000\" step=\"100\" value=\"{m_min_area}\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Dilation kernel (px): <output id=\"md_kernel_out\">{m_kernel}</output></span>
                            <input type=\"range\" name=\"md_kernel\" min=\"1\" max=\"41\" step=\"2\" value=\"{m_kernel}\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Dilation iterations: <output id=\"md_iterations_out\">{m_iters}</output></span>
                            <input type=\"range\" name=\"md_iterations\" min=\"0\" max=\"5\" step=\"1\" value=\"{m_iters}\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Box padding (px): <output id=\"md_pad_out\">{m_pad}</output></span>
                            <input type=\"range\" name=\"md_pad\" min=\"0\" max=\"50\" step=\"1\" value=\"{m_pad}\">
                        </label>
                    </div>
                </fieldset>
                <p><button type=\"submit\">Save</button></p>
            </form>
            <form method=\"post\" action=\"/settings\" style=\"margin-top:10px;\"> 
                <input type=\"hidden\" name=\"action\" value=\"reset_motion\"> 
                <button type=\"submit\">Reset Motion Sensitivity to Defaults</button> 
            </form>
            <form method=\"post\" action=\"/settings\" style=\"margin-top:10px;\"> 
                <input type=\"hidden\" name=\"action\" value=\"reset_face_manifest\"> 
                <button type=\"submit\">Reset Unknown Face Manifest</button> 
            </form>
            {unknowns_html}
        </div>
        <script>
        (function() {{
            function bind(name) {{
                var input = document.querySelector('input[name="' + name + '"]');
                var out = document.getElementById(name + '_out');
                if (!input || !out) return;
                function update() {{ out.textContent = input.value; }}
                input.addEventListener('input', update);
                update();
            }}
            ['md_threshold','md_min_area','md_kernel','md_iterations','md_pad'].forEach(bind);
            ['cam_fps','stream_jpeg_quality','stream_raw_fps'].forEach(bind);

            // OAuth2 settings toggle
            var authModeRadios = document.querySelectorAll('input[name="auth_mode"]');
            var oauth2Settings = document.getElementById('oauth2_settings');
            authModeRadios.forEach(function(radio) {{
                radio.addEventListener('change', function() {{
                    if (this.value === 'oauth2') {{
                        oauth2Settings.style.display = 'block';
                    }} else {{
                        oauth2Settings.style.display = 'none';
                    }}
                }});
            }});

            // OAuth2 test button
            var testBtn = document.getElementById('oauth2_test_btn');
            var testResult = document.getElementById('oauth2_test_result');
            if (testBtn) {{
                testBtn.addEventListener('click', function() {{
                    var baseUrl = document.querySelector('input[name="oauth2_base_url"]').value;
                    if (!baseUrl) {{
                        testResult.className = 'error';
                        testResult.style.display = 'block';
                        testResult.textContent = 'Please enter an OAuth2 Server Base URL';
                        return;
                    }}
                    testBtn.disabled = true;
                    testBtn.textContent = 'Testing...';
                    testResult.style.display = 'none';

                    fetch('/api/oauth2/test?base_url=' + encodeURIComponent(baseUrl))
                        .then(function(r) {{ return r.json(); }})
                        .then(function(data) {{
                            testBtn.disabled = false;
                            testBtn.textContent = 'Test OAuth2 Connection';
                            testResult.style.display = 'block';
                            if (data.ok) {{
                                testResult.className = 'success';
                                testResult.textContent = 'Success! Connected to: ' + (data.issuer || baseUrl);
                            }} else {{
                                testResult.className = 'error';
                                testResult.textContent = 'Error: ' + (data.error || 'Unknown error');
                            }}
                        }})
                        .catch(function(err) {{
                            testBtn.disabled = false;
                            testBtn.textContent = 'Test OAuth2 Connection';
                            testResult.style.display = 'block';
                            testResult.className = 'error';
                            testResult.textContent = 'Error: ' + err.message;
                        }});
                }});
            }}
        }})();
        </script>
    </body>
    </html>
    """
