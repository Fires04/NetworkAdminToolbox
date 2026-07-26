"""proxy.py - reverse-proxy helpers for mounting a sub-app's own web server
under /app/<name>/ on the toolbox's host:port.

Sub-apps assume they're served from the domain root, so any HTML response
they return needs its root-absolute path literals (fetch('/x'), href="/x",
`/x` in inline JS) rewritten to include the mount prefix -- otherwise the
browser would resolve them against the toolbox's root instead of the
sub-app's mount point.
"""
import re
import urllib.error
import urllib.request

REQUEST_TIMEOUT = 30

# Headers that are connection-specific to one hop and must not be replayed
# on the other side of the proxy (RFC 7230 6.1, plus content-length/encoding
# since the body length changes when we rewrite HTML).
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "content-encoding", "content-length", "host",
}

# Root-absolute path literals worth rewriting, scoped to contexts where a
# JS regex literal (e.g. `.replace(/&/g, ...)`) can't appear -- a blind
# "quote immediately followed by /" match also fires inside those regex
# literals (the closing "/" of /"/g reads as a quote-then-slash) and
# corrupts them. Each pattern here anchors on something a regex literal
# argument never has: an HTML attribute name, or the literal "fetch(".
_ATTR_PATH_RE = re.compile(r'((?:href|src|action)=)([\'"])/(?!/)')
_FETCH_PATH_RE = re.compile(r'(fetch\(\s*)([\'"`])/(?!/)')
_TEMPLATE_PATH_RE = re.compile(r'(`)/(?!/)')

_BANNER_CSS = (
    "position:sticky;top:0;z-index:9999;background:#20232a;color:#e6e6e6;"
    "font:13px/1 -apple-system,Segoe UI,sans-serif;padding:.5rem 1rem;"
    "display:flex;gap:.75rem;align-items:center;border-bottom:1px solid #3a3f4b;"
)
_BANNER_LINK_CSS = "color:#8ab4f8;text-decoration:none;"


def _display_name(name):
    return name.replace("-", " ").replace("_", " ").title()


def _inject_banner(html_text, name):
    banner = (
        f'<div style="{_BANNER_CSS}">'
        f'<a href="/" style="{_BANNER_LINK_CSS}">&larr; PyFNetwork Toolbox</a>'
        f'<span style="opacity:.6">/ {_display_name(name)}</span>'
        f'</div>'
    )
    if "<body" in html_text:
        return re.sub(r'(<body[^>]*>)', r'\1' + banner, html_text, count=1)
    return banner + html_text


def rewrite_html(body_bytes, prefix, name):
    text = body_bytes.decode("utf-8", errors="replace")
    text = _ATTR_PATH_RE.sub(rf'\1\2{prefix}/', text)
    text = _FETCH_PATH_RE.sub(rf'\1\2{prefix}/', text)
    text = _TEMPLATE_PATH_RE.sub(rf'\1{prefix}/', text)
    text = _inject_banner(text, name)
    return text.encode("utf-8")


def forward(request, target_url):
    """Forward a Flask `request` to target_url and return (body, status, headers)."""
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
    req = urllib.request.Request(
        target_url, data=request.get_data() or None,
        method=request.method, headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read(), resp.status, list(resp.getheaders())
    except urllib.error.HTTPError as e:
        return e.read(), e.code, list((e.headers or {}).items())
