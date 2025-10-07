from typing import Set, List


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

    return f"""
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
        <title>OpenSentry Settings</title>
        <style>
            body {{ font-family: system-ui, Arial, sans-serif; line-height: 1.4; }}
            .form-wrap {{ max-width: 960px; margin: 0 auto; padding: 0 16px; }}
            fieldset {{ border: 1px solid #ccc; border-radius: 6px; padding: 12px; margin-top: 12px; }}
            .options-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px 16px; align-items: center; }}
            .options-grid label {{ display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }}
            .status-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px 14px; align-items: center; }}
            .status-item {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border: 1px solid #eee; border-radius: 6px; }}
            .pill {{ padding: 2px 8px; border-radius: 12px; font-weight: 600; font-size: 0.9em; border: 1px solid transparent; }}
            .pill.ok {{ background: #e6f4ea; color: #136b2d; border-color: #cde9d6; }}
            .md-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px 18px; align-items: start; }}
            .md-grid .control {{ display: flex; flex-direction: column; gap: 6px; }}
            .md-grid .control .control-title {{ display: flex; gap: 8px; align-items: baseline; justify-content: space-between; }}
            .md-grid .control output {{ font-variant-numeric: tabular-nums; min-width: 3ch; text-align: right; }}
            .md-grid input[type=range] {{ width: 100%; }}
            .unknowns-grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap:12px; }}
            .unknowns-grid .card {{ border:1px solid #ddd; border-radius:6px; overflow:hidden; display:flex; flex-direction:column; }}
            .unknowns-grid .img img {{ width:100%; display:block; }}
            .unknowns-grid .meta {{ padding:8px; display:flex; justify-content:space-between; align-items:center; }}
            .unknowns-grid .actions {{ display:flex; gap:8px; padding:8px; align-items:center; border-top:1px solid #eee; flex-wrap: wrap; }}
            .unknowns-grid .actions input[type=text] {{ flex: 1 1 240px; min-width: 240px; padding:8px; font-size: 14px; }}
            .unknowns-grid .actions button {{ padding:8px 12px; }}
        </style>
    </head>
    <body>
        <center>
            <p><a href=\"/\">Back to Home</a></p>
        </center>
        <div class=\"form-wrap\">
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
        }})();
        </script>
    </body>
    </html>
    """
