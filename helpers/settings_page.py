from typing import Set, List
from helpers.theme import get_css, header_html


def render_settings_page(
    *,
    m_min_area: int,
    m_pad: int,
    raw_ok: bool,
    motion_ok: bool,
    device_id: str = '',
    port: int = 5000,
    mdns_enabled: bool = True,
    app_version: str = '',
    auth_mode: str = 'local',
    oauth2_base_url: str = '',
    oauth2_client_id: str = '',
    oauth2_client_secret: str = '',
    oauth2_scope: str = 'openid profile email offline_access',
    # Snapshot settings (snapshot-only mode)
    snapshot_interval: int = 10,
    snapshot_motion_detection: bool = True,
    snapshot_retention_count: int = 100,
    snapshot_retention_days: int = 7,
    snapshot_directory: str = 'snapshots',
) -> str:
    # OAuth2 settings
    auth_mode_local_checked = 'checked' if auth_mode == 'local' else ''
    auth_mode_oauth2_checked = 'checked' if auth_mode == 'oauth2' else ''

    raw_class = 'ok' if raw_ok else 'down'
    raw_text = 'Active' if raw_ok else 'Down'
    motion_class = 'ok' if motion_ok else 'down'
    motion_text = 'Active' if motion_ok else 'Down'

    css = get_css() + """
            .form-wrap { max-width: 1040px; margin: 0 auto; padding: 16px; }
            fieldset { border: 1px solid var(--border); background: var(--surface); border-radius: 10px; padding: 14px; margin-top: 14px; }
            legend { color: var(--muted); }
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
            input[type=text], input[type=number] { background:#0e131b; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; }
            input[type=checkbox], input[type=radio] { accent-color: var(--accent); }
            button { background: var(--accent); color:#fff; border:0; padding:8px 12px; border-radius:8px; font-weight:600; cursor:pointer; }
            button:hover { filter: brightness(1.05); }
            .auth-mode-options { display:flex; gap:16px; margin:12px 0; }
            .oauth2-fields { display:grid; gap:12px; margin-top:12px; }
            .oauth2-fields label { display:flex; flex-direction:column; gap:4px; }
            .oauth2-fields input[type=text] { width:100%; }
            #oauth2_test_btn { margin-top:8px; }
            #oauth2_test_result { margin-top:8px; padding:8px; border-radius:6px; display:none; }
            #oauth2_test_result.success { background:rgba(22,163,74,0.15); color:#86efac; border:1px solid rgba(22,163,74,0.35); }
            #oauth2_test_result.error { background:rgba(239,68,68,0.15); color:#fecaca; border:1px solid rgba(239,68,68,0.35); }
    """
    hdr = header_html('Settings - Motion Detection Camera')

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
                </div>
            </fieldset>
            <form method=\"post\" action=\"/settings\">
                <fieldset>
                    <legend>Snapshot Settings (Interval-Based Capture)</legend>
                    <div class=\"md-grid\">
                        <label class=\"control\">
                            <span class=\"control-title\">Capture interval (sec): <output id=\"snapshot_interval_out\">{snapshot_interval}</output></span>
                            <input type=\"range\" name=\"snapshot_interval\" min=\"5\" max=\"60\" step=\"1\" value=\"{snapshot_interval}\" oninput=\"document.getElementById('snapshot_interval_out').textContent=this.value\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Retention count: <output id=\"snapshot_retention_count_out\">{snapshot_retention_count}</output></span>
                            <input type=\"range\" name=\"snapshot_retention_count\" min=\"10\" max=\"1000\" step=\"10\" value=\"{snapshot_retention_count}\" oninput=\"document.getElementById('snapshot_retention_count_out').textContent=this.value\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Retention days: <output id=\"snapshot_retention_days_out\">{snapshot_retention_days}</output></span>
                            <input type=\"range\" name=\"snapshot_retention_days\" min=\"1\" max=\"30\" step=\"1\" value=\"{snapshot_retention_days}\" oninput=\"document.getElementById('snapshot_retention_days_out').textContent=this.value\">
                        </label>
                        <label class=\"control\" style=\"grid-column: 1 / -1;\">
                            <span class=\"control-title\">Snapshots directory</span>
                            <input type=\"text\" name=\"snapshot_directory\" value=\"{snapshot_directory}\" style=\"width:100%;\">
                        </label>
                    </div>
                    <div style=\"margin-top:12px;\">
                        <label><input type=\"checkbox\" name=\"snapshot_motion_detection\" {'checked' if snapshot_motion_detection else ''}> Enable motion detection overlay on snapshots</label>
                    </div>
                    <p><small><strong>Capture interval:</strong> Time between snapshots (5-60 seconds). <strong>Retention:</strong> Keep last N snapshots or X days (whichever limit is hit first). Motion detection adds green boxes around detected movement.</small></p>
                </fieldset>
                <fieldset>
                    <legend>Motion Detection Settings</legend>
                    <div class=\"md-grid\">
                        <label class=\"control\">
                            <span class=\"control-title\">Min area (px): <output id=\"md_min_area_out\">{m_min_area}</output></span>
                            <input type=\"range\" name=\"md_min_area\" min=\"0\" max=\"50000\" step=\"100\" value=\"{m_min_area}\" oninput=\"document.getElementById('md_min_area_out').textContent=this.value\">
                        </label>
                        <label class=\"control\">
                            <span class=\"control-title\">Box padding (px): <output id=\"md_pad_out\">{m_pad}</output></span>
                            <input type=\"range\" name=\"md_pad\" min=\"0\" max=\"50\" step=\"1\" value=\"{m_pad}\" oninput=\"document.getElementById('md_pad_out').textContent=this.value\">
                        </label>
                    </div>
                    <p><small><strong>Min area:</strong> Minimum contour size to detect as motion (higher = less sensitive, fewer false positives). <strong>Padding:</strong> Pixels added around detected motion boxes. Uses lightweight frame differencing for low CPU usage.</small></p>
                </fieldset>
                <p><button type=\"submit\">Save</button></p>
            </form>
            <form method=\"post\" action=\"/settings\" style=\"margin-top:10px;\"> 
                <input type=\"hidden\" name=\"action\" value=\"reset_motion\"> 
                <button type=\"submit\">Reset Motion Sensitivity to Defaults</button> 
            </form>
            
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
            ['md_min_area','md_pad'].forEach(bind);
            ['snapshot_interval','snapshot_retention_count','snapshot_retention_days'].forEach(bind);

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
