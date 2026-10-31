"""Shared origin checks for browser writes and safe navigation destinations."""
import re
from urllib.parse import unquote, urlsplit


SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})

# Only these POST contracts are independent of ambient login cookies.
# Full route matching prevents future children of a public prefix inheriting
# an exemption. Each handler must retain its own token/validation controls.
CSRF_EXCEPTIONS = {
    '/offsite-backup/ping': 'Shared X-Backup-Token secret; no session authority',
    '/integrations/telegram/webhook': 'Telegram secret header; neutral private help only, no session authority',
    '/integrations/telegram/outbound-permit': 'Signed bot-source request and one-time eligible delivery lease; no session authority',
    '/integrations/gmail/documents': 'Timestamped body HMAC; no session authority',
    '/r/{qr_token}': 'Public survey token, response window and submission deduplication',
    '/seq': 'Public survey tokens, response windows and submission deduplication',
    '/e/{event_token}': 'Public event registration token and registration validation',
    '/e/{event_token}/email-link': 'Public event token and rate-limited email-link recovery',
    '/room': 'Anonymous external room request; rate limit, honeypot and validation',
    '/room/t/{token}/withdraw': 'Signed room tracking token; external reservation only',
    '/room/t/{token}/take': 'Signed room tracking token; external reservation only',
    '/room/t/{token}/meals': 'Signed room tracking token; external reservation only',
    '/room/t/{token}/meals/start': 'Signed room tracking token; external reservation only',
    '/rooms/decide/{rid}': 'Signed room decision token; current approver checked by handler',
    '/wellness/decide/{claim_id}': 'Signed decision token; current approver checked by handler',
    '/whereabouts/week': 'Signed user/week token; no session authority',
}
_EXEMPT_PATTERNS = tuple(re.compile('^' + re.sub(r'\\\{[^}]+\\\}', '[^/]+',
                                              re.escape(path)) + '$')
                         for path in CSRF_EXCEPTIONS)


def csrf_exempt(method, path):
    return method == 'POST' and any(pattern.fullmatch(path) for pattern in _EXEMPT_PATTERNS)


def _origin(value, *, allow_path=False):
    """Parse an HTTP origin strictly, including scheme and effective port."""
    if (not isinstance(value, str) or not value or len(value) > 8192
            or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or '\\' in value):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or ',' in parsed.netloc
                or parsed.username is not None or parsed.password is not None
                or (not allow_path and (parsed.path not in ('', '/')
                                        or parsed.query or parsed.fragment))):
            return None
        host = parsed.hostname.encode('idna').decode('ascii').lower()
        port = parsed.port
        return parsed.scheme, host, port if port is not None else (443 if parsed.scheme == 'https' else 80)
    except (ValueError, UnicodeError):
        return None


def same_origin_write(request, canonical_origin=None):
    """Require an exact Origin or, when absent, an exact Referer origin.

    Neither SameSite cookies nor an absent header is sufficient. Raw forwarded
    headers are not trusted. canonical_origin comes only from server config;
    otherwise the ASGI request origin must reflect the trusted proxy setup.
    This does not replace session authorization or module-specific CSRF tokens.
    """
    expected = _origin(canonical_origin or str(request.base_url))
    if expected is None:
        return False
    if request.headers.get('sec-fetch-site', '').lower() == 'cross-site':
        return False
    seen = False
    for header in ('origin', 'referer'):
        values = request.headers.getlist(header)
        if not values:
            continue
        seen = True
        if len(values) != 1 or _origin(values[0], allow_path=header == 'referer') != expected:
            return False
    return seen


def safe_local_return(value, default='/'):
    """Return an absolute local path unchanged, or a trusted caller fallback.

    Inspect successive percent-decoded forms to reject ambiguous separators
    and controls without decoding legitimate query values in the returned URL.
    The fallback must be a fixed application-owned destination.
    """
    if not isinstance(value, str) or not value or len(value) > 4096:
        return default
    candidate = value
    for _ in range(8):
        if (not candidate.startswith('/') or candidate.startswith('//')
                or '\\' in candidate
                or any(ord(char) < 32 or ord(char) == 127 for char in candidate)):
            return default
        try:
            parts = urlsplit(candidate)
            if parts.scheme or parts.netloc:
                return default
            decoded = unquote(candidate, errors='strict')
        except (ValueError, UnicodeError):
            return default
        if decoded == candidate:
            return value
        candidate = decoded
    # Refuse excessive nesting rather than accept an incompletely checked URL.
    return default
