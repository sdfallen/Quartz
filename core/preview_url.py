"""Which addresses the app preview may open.

The preview shows an application the user or an agent is building on this
computer. It is limited to loopback web addresses so that a reply, a page or a
log line can never turn the preview into a general browser inside SpeS.
Standard library only; the JavaScript twin lives in ``ui/js_preview.py``.
"""
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048
PROBE_TIMEOUT_SECONDS = 2.0
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class PreviewUrlError(ValueError):
    """The address is not a local web address the preview may open."""


def _is_loopback(host):
    host = host.lower().rstrip(".")
    return host in LOOPBACK_HOSTS or host.endswith(".localhost")


def normalize_preview_url(value):
    """Return a normalised ``http(s)://loopback[:port]/path`` URL or raise.

    A bare ``host:port`` or ``:port`` is read as ``http://``. User info,
    non-web schemes, non-loopback hosts and over-long or control-character
    addresses are refused.
    """
    if not isinstance(value, str):
        raise PreviewUrlError("Adres metin olmalı")
    text = value.strip()
    if not text or len(text) > MAX_URL_LENGTH:
        raise PreviewUrlError("Adres boş ya da çok uzun")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in text):
        raise PreviewUrlError("Adreste boşluk veya denetim karakteri var")
    if text.startswith(":") and text[1:].split("/", 1)[0].isdigit():
        text = "localhost" + text
    if "://" not in text:
        text = "http://" + text
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise PreviewUrlError("Adres çözümlenemedi") from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise PreviewUrlError("Yalnız http veya https adresleri açılabilir")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise PreviewUrlError("Adreste kullanıcı bilgisi olamaz")
    host = parts.hostname or ""
    if not _is_loopback(host):
        raise PreviewUrlError("Önizleme yalnız bu bilgisayardaki adresleri açar (localhost, 127.0.0.1)")
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, parts.fragment))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A probe never follows a redirect: it could leave the loopback host."""

    def redirect_request(self, *args, **kwargs):
        return None


def _forbids_framing(headers):
    xfo = (headers.get("X-Frame-Options") or "").strip().lower()
    if xfo in ("deny", "sameorigin") or xfo.startswith("allow-from"):
        return True
    for policy in headers.get_all("Content-Security-Policy") or []:
        for directive in policy.split(";"):
            name, _, value = directive.strip().partition(" ")
            if name.lower() == "frame-ancestors" and value.strip() not in ("*", ""):
                return True
    return False


def frame_policy(url, timeout=PROBE_TIMEOUT_SECONDS, opener=None):
    """Ask a loopback app whether it can be shown inside the preview pane.

    Returns ``"allowed"``, ``"blocked"`` (the app forbids framing, so it must
    open in its own window) or ``"unreachable"`` (nothing answers there).
    ``url`` must already be normalised; non-loopback input raises.
    """
    target = normalize_preview_url(url)
    opener = opener or urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))
    for _hop in range(4):
        request = urllib.request.Request(target, method="GET", headers={"User-Agent": "SpeS-Preview"})
        try:
            with opener.open(request, timeout=timeout) as response:
                return "blocked" if _forbids_framing(response.headers) else "allowed"
        except urllib.error.HTTPError as exc:
            if _forbids_framing(exc.headers):
                return "blocked"
            location = exc.headers.get("Location") if 300 <= exc.code < 400 else None
            if not location:
                return "allowed"
            try:  # Follow only to another loopback address, at most three hops.
                target = normalize_preview_url(urllib.parse.urljoin(target, location))
            except PreviewUrlError:
                return "allowed"
        except (urllib.error.URLError, OSError, ValueError):
            return "unreachable"
    return "allowed"
