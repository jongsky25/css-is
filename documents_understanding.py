"""Conservative, bounded request extraction; no model calls or automatic routing."""
import json
import re
from datetime import date

MAX_REQUESTS = 5
# Starter vocabulary, not an organizational routing policy.
FOCUS_AREAS = {
    'governance': 'Local health systems governance',
    'financing': 'Health financing',
    'workforce': 'Health workforce',
    'service_delivery': 'Health service delivery',
    'information': 'Health information and reporting',
    'capacity': 'Capacity development',
    'administration': 'Administration and operations',
}
TERMS = {
    'governance': ('local health system', 'local health board', 'health governance'),
    'financing': ('health financing', 'special health fund', 'health budget'),
    'workforce': ('health workforce', 'human resources for health'),
    'service_delivery': ('service delivery network', 'primary care', 'referral system'),
    'information': ('health information', 'health data', 'health reporting'),
    'capacity': ('capacity development', 'capacity building'),
    'administration': ('procurement', 'administrative services'),
}
LIMITS = {'action': 700, 'output': 500, 'recipient': 300, 'deadline': 10,
          'submission': 500, 'evidence': 1000, 'page': 50, 'kind': 30, 'confirmed': 3}
FIELDS = tuple(f'need_{i}_{key}' for i in range(MAX_REQUESTS) for key in LIMITS) + (
    'focus_primary', 'focus_secondary', 'focus_evidence', 'focus_confirmed', 'needs_status', 'needs_status_confirmed')
REQUEST = re.compile(r'\b(?:please|kindly)\s+(?:(?:\w+)\s+){0,3}?(submit|provide|review|approve|nominate|attend|send|prepare|complete|accomplish|designate|confirm|furnish)\b|\b(?:requested|required)\s+to\s+(submit|provide|review|approve|nominate|attend|send|prepare|complete|accomplish|designate|confirm|furnish)\b', re.I)


_MONTH = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
_DATE = rf'(?:\d{{4}}-\d{{2}}-\d{{2}}|{_MONTH}\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+{_MONTH}\s+\d{{4}})'
_DUE = re.compile(r'\b(?:on or before|not later than|no later than|by)\s+|\bdeadline\s*:\s*', re.I)
_DATE_AT_START = re.compile(rf'({_DATE})(?![\w/-])', re.I)


def _explicit_date(value):
    from datetime import datetime
    for pattern in ('%Y-%m-%d', '%B %d, %Y', '%B %d %Y', '%d %B %Y'):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    return ''


def request_details(passage, match):
    """Only extract details inside this request's own bounded passage."""
    result = {'output': '', 'recipient': '', 'deadline': '', 'submission': '',
              'detail_evidence': {}, 'warnings': []}
    def keep(key, value, evidence=None):
        value = value.strip(' ,;:.')
        if value and len(value) <= LIMITS[key]:
            result[key] = value
            result['detail_evidence'][key] = evidence or value
    verb = next(group for group in match.groups() if group).casefold()
    if verb in ('submit', 'provide', 'send', 'prepare', 'complete', 'accomplish', 'furnish'):
        remainder = passage[match.end():].strip()
        output = re.split(r'\s+(?:on or before|not later than|no later than|by|via|through|to|using)\b|[.;]', remainder, maxsplit=1, flags=re.I)[0]
        if output.casefold().strip(' .') not in ('', 'it', 'this', 'that', 'them', 'these', 'those'):
            keep('output', output)
    # Only an explicitly named subject immediately before "are/is requested".
    prefix = passage[:match.start()]
    addressed = re.fullmatch(r'([A-Za-z][A-Za-z0-9 ,/&()’-]{1,150}?)\s+(?:are|is)\s+', prefix)
    if addressed and addressed[1].casefold() not in ('you', 'we', 'they', 'it'):
        keep('recipient', addressed[1])
    deadlines, uncertain = [], False
    for marker in _DUE.finditer(passage):
        tail = passage[marker.end():]
        found = _DATE_AT_START.match(tail)
        if not found:
            # "by email" identifies a channel, not an unclear due date.
            if not re.match(r'(?:email|e-mail|post|courier|hand)\b',tail,re.I): uncertain = True
            continue
        value = _explicit_date(found[1])
        if not value or re.match(r'\s*,?\s*(?:or|and|/|–|-)\s*\S', tail[found.end():], re.I):
            uncertain = True
        else:
            deadlines.append((value, passage[marker.start():marker.end()+found.end()]))
    if len({value for value,_ in deadlines}) == 1 and not uncertain:
        keep('deadline', deadlines[0][0], deadlines[0][1])
    elif deadlines or uncertain or re.search(r'\bwithin\s+\d+\s+(?:working\s+|calendar\s+)?days?\b',passage,re.I):
        result['warnings'].append('Deadline unclear or conflicting; enter it only after checking the source. Relative dates are not calculated.')
    channel = re.search(r'\b(?:via|through|using|by email(?: at)?|by e-mail(?: at)?)\s+(.+)',passage,re.I)
    if channel:
        instruction = re.split(r'\s+(?:on or before|not later than|no later than|by)\s+(?=\d|'+_MONTH+r'\b)|;|\.(?:\s|$)',channel[0],maxsplit=1,flags=re.I)[0]
        keep('submission', instruction)
    else:
        destination = re.search(r'\bto\s+([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|https://[^\s<>]+)',passage,re.I)
        if destination: keep('submission', destination[0])
    return result


def suggest(pages, numbers=None):
    requests, focus, seen = [], [], set()
    info = False
    for number, text in zip(numbers or range(1, len(pages)+1), pages):
        # Joining wrapped lines retains requests split by OCR, with bounded windows.
        sentences = re.split(r'(?<=[.!?])\s+|\n\s*\n', text[:100000])
        for sentence in sentences:
            sentence = ' '.join(sentence.split())
            matches = list(REQUEST.finditer(sentence))
            for index, match in enumerate(matches):
                if re.search(r'\b(?:not|never)\b', match[0], re.I) or re.search(r'\b(?:not|never|no longer)\s*$', sentence[max(0,match.start()-20):match.start()], re.I):
                    continue
                end = matches[index+1].start() if index+1 < len(matches) else len(sentence)
                start = max(0, match.start()-100) if index == 0 else match.start()
                passage = sentence[start:min(end,match.start()+600)].strip()
                key = passage.casefold()
                if key not in seen:
                    seen.add(key)
                    local_match = REQUEST.search(passage)
                    details = request_details(passage, local_match)
                    if start > 0:
                        details['recipient'] = ''
                        details['detail_evidence'].pop('recipient', None)
                    if end > match.start()+600:
                        details['warnings'].append('Request passage truncated; review the full source for remaining details.')
                    requests.append({'action': sentence[match.start():min(end,match.start()+600)].strip(),
                                     'kind': 'explicit', 'evidence': passage, 'page': str(number), **details})
            if re.search(r'\bfor (?:your )?information only\b', sentence, re.I):
                info = True
        for key, terms in TERMS.items():
            for term in terms:
                match = re.search(r'\b' + re.escape(term) + r's?\b', text, re.I)
                if match and key not in [item['value'] for item in focus]:
                    passage = next((part for part in sentences if re.search(r'\b'+re.escape(term)+r's?\b',part,re.I)), term)
                    start = max(0, passage.casefold().find(term)-80)
                    focus.append({'value': key, 'label': FOCUS_AREAS[key], 'page': str(number),
                                  'evidence': ' '.join(passage[start:start+500].split())})
                    break
    return {'requests': requests[:MAX_REQUESTS], 'focus': focus,
            'status': 'requests' if requests else 'information_only' if info else 'unclear',
            'warning': ('More than five possible requests found; review and record remaining requests separately. ' if len(requests)>MAX_REQUESTS else '') +
                       'Only supplied text was checked. Suggestions may miss requests; review all relevant pages. Blank details mean not captured, not absent.'}


def clean(fields, *, require_confirmation=False):
    result = {}
    for key in FIELDS:
        value = fields.get(key, '')
        if not isinstance(value, str):
            raise ValueError('Invalid document understanding field.')
        value = value.strip()
        limit = LIMITS[key.split('_', 2)[2]] if key.startswith('need_') else 1000 if key == 'focus_evidence' else 40
        if len(value) > limit:
            raise ValueError('Document understanding field is too long.')
        result[key] = value
    for i in range(MAX_REQUESTS):
        prefix = f'need_{i}_'
        populated = any(result[prefix+k] for k in LIMITS if k not in ('kind', 'confirmed'))
        if not populated:
            continue
        if not result[prefix+'action']:
            raise ValueError('Enter the requested action for each populated request.')
        if result[prefix+'kind'] not in ('explicit', 'inferred', 'manual', 'unclear'):
            raise ValueError('Choose the request interpretation.')
        deadline = result[prefix+'deadline']
        if deadline:
            try:
                if date.fromisoformat(deadline).isoformat() != deadline: raise ValueError()
            except ValueError:
                raise ValueError('Enter an unambiguous request deadline.') from None
        if require_confirmation and result[prefix+'confirmed'] != 'yes':
            raise ValueError('Confirm each populated request against the source before registering.')
    for key in ('focus_primary', 'focus_secondary'):
        if result[key] and result[key] not in FOCUS_AREAS:
            raise ValueError('Choose a supported focus area or leave it unclassified.')
    if result['focus_secondary'] and (not result['focus_primary'] or result['focus_primary']==result['focus_secondary']):
        raise ValueError('Choose a distinct secondary focus area after the primary area.')
    if require_confirmation and (result['focus_primary'] or result['focus_evidence']) and result['focus_confirmed'] != 'yes':
        raise ValueError('Confirm the focus area against the source before registering.')
    if result['needs_status'] not in ('', 'requests', 'information_only', 'unclear'):
        raise ValueError('Choose a supported request status.')
    has_requests = any(result[f'need_{i}_action'] for i in range(MAX_REQUESTS))
    if result['needs_status']=='requests' and not has_requests:
        raise ValueError('Add a request or mark the request status unclear.')
    if has_requests and not result['needs_status']: result['needs_status']='requests'
    if has_requests and result['needs_status'] == 'information_only':
        raise ValueError('A document with requests cannot be marked for information only.')
    if require_confirmation and result['needs_status']=='information_only' and result['needs_status_confirmed'] != 'yes':
        raise ValueError('Confirm that the source is for information only.')
    return result


def save(conn, doc_id, user, fields, timestamp):
    values = clean(fields, require_confirmation=True)
    if not any(value for key,value in values.items() if not key.endswith(('_kind', '_confirmed'))): return
    conn.execute('INSERT INTO document_understanding(document_id,values_json,actor_id,created_at) VALUES (?,?,?,?)',
                 (doc_id, json.dumps(values), user['id'], timestamp))


def read(conn, doc_id):
    row = conn.execute('SELECT values_json FROM document_understanding WHERE document_id=?', (doc_id,)).fetchone()
    return json.loads(row[0]) if row else {}
