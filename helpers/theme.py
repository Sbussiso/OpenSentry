from typing import List, Tuple


def get_css() -> str:
    """Shared dark theme CSS tokens and base elements (body, a, header).
    Pages can append their own specific CSS below this.
    """
    return (
        ":root { --bg:#0b0e14; --surface:#11161f; --text:#eaeef2; --muted:#93a3b5; --border:#2a3342; --accent:#3b82f6; }\n"
        "* { box-sizing: border-box; }\n"
        "body { margin:0; background:var(--bg); color:var(--text); font-family: system-ui, Arial, sans-serif; }\n"
        "a { color: var(--accent); text-decoration: none; }\n"
        "a:hover { text-decoration: underline; }\n"
        "header { background: var(--surface); border-bottom:1px solid var(--border); padding:10px 16px; display:flex; align-items:center; gap:12px; }\n"
        "header .spacer { flex:1; }\n"
        "header .links a { margin-left:12px; color: var(--muted); }\n"
    )


def header_html(title: str, links: List[Tuple[str, str]] | None = None) -> str:
    """Render a standard header bar.
    links: list of (href, label). Defaults to Home · Settings · Logout
    """
    if links is None:
        links = [
            ("/", "Home"),
            ("/settings", "Settings"),
            ("/logout", "Logout"),
        ]
    links_html = " · ".join(f"<a href='{href}'>{label}</a>" for href, label in links)
    return f"<header><strong>{title}</strong><div class='spacer'></div><div class='links'>{links_html}</div></header>"
