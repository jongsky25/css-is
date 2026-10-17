"""Transient PDF intake: no database, file writes, AI calls, or content logging."""
import http.client
import io
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit, urlencode

from dateutil.parser import parse as parse_date
from pypdf import PdfReader

MAX_BYTES = 6 * 1024 * 1024
MAX_PAGES = 50
MAX_TEXT = 100_000
FIELDS = {'subject': 500, 'type': 100, 'sender': 500, 'document_date': 10,
          'due_date': 10, 'references': 1000}


def public_target(url):
    """Resolve once and pin the connection to a public address (including redirects)."""
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or len(url) > 2048
            or any(ord(c) < 33 for c in url)):
        raise ValueError('Use a public HTTPS PDF link without credentials.')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('The PDF link must point to a public internet address.')
    return parsed, addresses[0][4][0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname, address, timeout):
        super().__init__(hostname, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch_pdf(url):
    """Bounded download; no cookies, credentials, proxies, or automatic redirects."""
    parsed = urlsplit(url)
    if parsed.hostname == 'drive.google.com':
        # Public Drive share links only. Private files can be selected locally.
        from documents_operations import validate_drive_url
        _, file_id = validate_drive_url(url)
        url = 'https://drive.google.com/uc?' + urlencode({'export': 'download', 'id': file_id})
    deadline = time.monotonic() + 20
    for _ in range(4):
        parsed, address = public_target(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Reading the PDF link timed out. Select the file instead.')
        conn = _PinnedHTTPS(parsed.hostname, address, min(remaining, 8))
        try:
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            conn.request('GET', path, headers={'Accept': 'application/pdf', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('The PDF link returned an invalid redirect.')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError('The PDF link is unavailable. Select the file or continue manually.')
            length = response.getheader('Content-Length')
            if length and int(length) > MAX_BYTES:
                raise ValueError('Choose a PDF no larger than 6 MiB.')
            raw = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('Reading the PDF link timed out.')
                # read1 avoids waiting for a whole chunk from a slow server.
                if conn.sock:
                    conn.sock.settimeout(min(remaining, 8))
                chunk = response.read1(min(65536, MAX_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise ValueError('Choose a PDF no larger than 6 MiB.')
            return bytes(raw)
        finally:
            conn.close()
    raise ValueError('The PDF link redirects too many times. Select the file instead.')


def _date(value):
    value = value.strip().rstrip('.')
    # Require an explicit year; never infer today's date or an ambiguous numeric date.
    if not re.search(r'\b(?:19|20)\d{2}\b', value):
        return ''
    if not (re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) or
            re.fullmatch(r'(?:[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})', value)):
        return ''
    try:
        return parse_date(value, fuzzy=False).date().isoformat()
    except (ValueError, OverflowError):
        return ''


def suggest(pages):
    candidates = {key: [] for key in FIELDS}
    patterns = {
        'subject': r'^subject(?:\s*[:\-]\s*|\s+)(.+)$',
        'sender': r'^(?:from|sender|originating office)(?:\s*[:\-]\s*|\s+)(.+)$',
        'type': r'^(?:document type|type)\s*[:\-]\s*(.+)$',
        'document_date': r'^(?:document date|date|dated)(?:\s*[:\-]\s*|\s+)(.+)$',
        'due_date': r'^(?:deadline|due date|due|on or before)\s*[:\-]?\s*(.+)$',
        'references': r'^((?:DTRAK\b|reference\b|ref\.).*)$',
    }
    label = re.compile(r'^(?:subject|from|sender|originating office|document type|type|document date|date|dated|deadline|due date|due|references?|DTRAK|to)\s*[:\-]?\s*$', re.I)
    boundary = re.compile(r'^(?:subject|from|sender|originating office|document type|type|document date|date|dated|deadline|due date|due|references?|DTRAK|to)(?:\s*[:\-]|\s*$)', re.I)
    for page_number, text in enumerate(pages, 1):
        lines = [re.sub(r'\s+', ' ', line.replace('：', ':')).strip() for line in text.splitlines()]
        combined = []
        index = 0
        while index < len(lines):
            line = lines[index]
            # A standalone label followed by its value is common in PDF text and OCR.
            if label.fullmatch(line) and index + 1 < len(lines):
                next_line = lines[index + 1]
                if next_line and not boundary.match(next_line):
                    line = line.rstrip(' :-') + ': ' + next_line
                    index += 1
            combined.append(line)
            index += 1
        for line in combined:
            for key, pattern in patterns.items():
                match = re.match(pattern, line, re.I)
                if match:
                    value = match[1].strip()
                    if key in ('document_date', 'due_date'):
                        value = _date(value)
                    if value and len(value) <= FIELDS[key]:
                        candidates[key].append((value, page_number, line[:600]))
            heading = re.fullmatch(r'(memorandum|memo|letter|advisory|office order|department order|department memorandum|administrative order|invitation)(?:\s+(?:no\.?|number)\s*[:.]?\s*([A-Z0-9][A-Z0-9./ -]{0,60}))?', line, re.I)
            if heading:
                candidates['type'].append((heading[1], page_number, line))
                if heading[2]:
                    candidates['references'].append((line, page_number, line))
    suggestions, evidence, warnings = {}, {}, []
    for key, found in candidates.items():
        unique = list(dict.fromkeys(item[0] for item in found))
        if key == 'references' and unique:
            value = '\n'.join(unique)
            if len(value) <= FIELDS[key]:
                suggestions[key] = value
                evidence[key] = [{'page': p, 'text': t} for _, p, t in found[:8]]
        elif len(unique) == 1:
            suggestions[key] = unique[0]
            evidence[key] = [{'page': found[0][1], 'text': found[0][2]}]
        elif len(unique) > 1:
            warnings.append('Multiple values found for ' + key.replace('_', ' ') + '; enter it manually.')
    if not suggestions:
        warnings.append('No clearly labelled fields were found. Enter the details manually.')
    return {'suggestions': suggestions, 'evidence': evidence, 'warnings': warnings,
            'notice': 'Suggested values are unverified. Check each value against the PDF before registration.'}


def read_pdf(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Choose a PDF no larger than 6 MiB.')
    if not raw.startswith(b'%PDF-'):
        raise ValueError('This is not a PDF file. For private links, select the PDF from your device.')
    try:
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise ValueError('Password-protected PDFs are not supported. Continue manually.')
        if len(reader.pages) > MAX_PAGES:
            raise ValueError('Choose a PDF with at most 50 pages.')
        pages, total, scanned = [], 0, []
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            total += len(text)
            if total > MAX_TEXT:
                raise ValueError('This PDF contains too much text. Continue manually.')
            pages.append(text)
            # Sparse text may be a header/footer on an otherwise scanned page.
            if len(re.sub(r'\W', '', text)) < 40:
                scanned.append(index)
        if scanned:
            import documents_ocr
            readings = documents_ocr.read_pages(raw, scanned)
            for index, text in readings.items():
                # Keep native text if OCR found nothing; otherwise use the complete
                # rendered page, avoiding duplicate/conflicting header suggestions.
                if text.strip():
                    pages[index] = text
            if sum(map(len, pages)) > MAX_TEXT:
                raise ValueError('This PDF contains too much text. Continue manually.')
    except ValueError:
        raise
    except Exception:
        raise ValueError('The PDF could not be read. Continue manually.') from None
    if not any(text.strip() for text in pages):
        raise ValueError('No readable text was found, including after OCR. Try a clearer scan or enter the details manually.')
    result = suggest(pages)
    result['reading'] = {'page_count': len(pages), 'ocr_pages': [i + 1 for i in scanned]}
    # Bounded, transient preview even when no labelled fields can be suggested.
    result['text_preview'] = [{'page': i + 1, 'text': text[:2000], 'truncated': len(text) > 2000}
                              for i, text in enumerate(pages[:10])]
    result['preview_truncated'] = len(pages) > 10
    if scanned:
        result['warnings'].insert(0, 'OCR was used on pages ' + ', '.join(str(i + 1) for i in scanned) + '. Check names, numbers and dates against the scan.')
    return result
