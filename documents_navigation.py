"""Bounded queue context carried in URLs, never used as authorization."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

QUEUE_FIELDS = {
    '/documents': {'queue', 'q', 'before', 'interactive', 'status', 'verification',
                   'deadline', 'lead_id', 'due_from', 'due_to', 'group_by', 'sort',
                   'dir', 'page', 'saved_view'},
    '/documents/actions': {'view', 'before', 'due'},
    '/documents/intake': {'state', 'page', 'review'},
}
ROW = re.compile(r'(?:document-row|registry-row|intake-row)-[0-9]+|document-step-[0-9]+-[0-9]+')
RECORD = re.compile(r'/documents/(?:intake/)?[0-9]+(?:/[A-Za-z0-9_/-]+)?')


def safe_return(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        return ''
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return ''
    try:
        parts = urlsplit(value)
        if parts.scheme or parts.netloc or parts.path not in QUEUE_FIELDS:
            return ''
        pairs = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=32)
        if any(any(ord(char) < 32 or ord(char) == 127 for char in key + val) for key, val in pairs):
            return ''
        fields = {key: val for key, val in pairs if key in QUEUE_FIELDS[parts.path]}
        fragment = parts.fragment if ROW.fullmatch(parts.fragment) else ''
        return urlunsplit(('', '', parts.path, urlencode(fields), fragment))
    except ValueError:
        return ''


def record_url(target, origin='', anchor=''):
    """Preserve target fragments; only attach a validated local queue URL."""
    origin = safe_return(origin)
    if not origin:
        return target
    if anchor and ROW.fullmatch(anchor):
        origin = origin.split('#', 1)[0] + '#' + anchor
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not RECORD.fullmatch(parts.path):
        return target
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'return_to']
    query.append(('return_to', origin))
    return urlunsplit(('', '', parts.path, urlencode(query), parts.fragment))


def context(request):
    path = request.url.path
    origin = (safe_return(path + ('?' + str(request.query_params) if request.query_params else ''))
              if path in QUEUE_FIELDS else safe_return(request.query_params.get('return_to', '')))
    label = {'/documents': 'Back to register', '/documents/actions': 'Back to My desk',
             '/documents/intake': 'Back to Inbox'}.get(urlsplit(origin).path, '')
    return {'return_url': origin, 'return_label': label,
            'show_queue_return': bool(origin and path not in QUEUE_FIELDS),
            'document_url': lambda target, anchor='': record_url(target, origin, anchor)}


def return_to_record(request, target):
    return record_url(target, request.query_params.get('return_to', ''))
