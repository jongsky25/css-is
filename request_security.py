"""Shared validation for browser-controlled navigation destinations."""
from urllib.parse import unquote, urlsplit


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
