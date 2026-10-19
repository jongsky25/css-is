"""Append-only page notes and exact-PDF ink tied to a document file version."""
import json
import re
import uuid
import tzutil
import documents as documents
import documents_permissions as permissions
from documents_storage import rows, transaction


def source(conn, user, document_id, version_id):
    doc = documents.get(conn, user, document_id)
    found = rows(conn, 'SELECT * FROM document_file_version WHERE id=? AND document_id=?',
                 (version_id, document_id))
    if not found:
        raise permissions.Denied('File version unavailable on this document.')
    return doc, found[0]


def list_for_version(conn, user, document_id, version_id):
    source(conn, user, document_id, version_id)
    return rows(conn, '''SELECT a.*,COALESCE(NULLIF(r.name,''),u.username) AS author
        FROM document_annotation a JOIN admin_user u ON u.id=a.actor_id
        LEFT JOIN resource_person r ON r.id=u.rp_id
        WHERE a.document_id=? AND a.version_id=? ORDER BY a.page_number,a.id''',
        (document_id, version_id))


def _allowed(conn, user, doc):
    return (permissions.can_work(conn, user, doc) or
            (doc['reviewer_id'] == user['id'] and doc['status'] == 'in_review'))


def _page(value):
    try:
        page = int(value)
    except (TypeError, ValueError):
        raise ValueError('Enter a page number between 1 and 500.') from None
    if not 1 <= page <= 500:
        raise ValueError('Enter a page number between 1 and 500.')
    return page


def _strokes(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 60:
        raise ValueError('Draw between 1 and 60 pen strokes.')
    normalized = []
    total = 0
    for stroke in value:
        if not isinstance(stroke, list) or not 2 <= len(stroke) <= 1000:
            raise ValueError('A pen stroke needs 2 to 1000 points.')
        points = []
        for point in stroke:
            if (not isinstance(point, list) or len(point) != 2 or
                    any(isinstance(n, bool) or not isinstance(n, (int, float)) or not 0 <= n <= 1 for n in point)):
                raise ValueError('Pen coordinates must stay on the page.')
            points.append([round(float(point[0]), 4), round(float(point[1]), 4)])
        normalized.append(points)
        total += len(points)
    if total > 4000:
        raise ValueError('This annotation has too many points. Save a smaller drawing.')
    return normalized


def save(conn, user, document_id, version_id, revision, page_number, *,
         body='', strokes=None, source_sha256='', adapter=None):
    user = permissions.actor(conn, user)
    doc, file_version = source(conn, user, document_id, version_id)
    documents.writable(conn)
    documents.require(_allowed(conn, user, doc))
    page = _page(page_number)
    body = str(body or '').strip()
    ink = strokes is not None
    if ink:
        strokes = _strokes(strokes)
        filing = conn.execute('''SELECT filing_state FROM document_intake
            WHERE document_id=? AND file_id=? ORDER BY id DESC LIMIT 1''',
            (document_id, file_version['file_id'])).fetchone()
        if filing and filing[0] not in ('complete', 'none'):
            raise ValueError('Wait for Drive filing to finish before marking this PDF.')
        if not re.fullmatch(r'[a-f0-9]{64}', source_sha256 or ''):
            raise ValueError('Select the matching PDF before saving pen marks.')
        if adapter is None:
            from documents_operations import get_adapter
            adapter = get_adapter()
        result = adapter.call('inspect', {'file_id': file_version['file_id'],
                              'actor_id': user['id'], 'max_bytes': 20 * 1024 * 1024}, str(uuid.uuid4()))
        if (result.get('accessible') is not True or result.get('file_id') != file_version['file_id'] or
                not result.get('fingerprint') or
                (file_version['fingerprint'] and result.get('fingerprint') != file_version['fingerprint']) or
                result.get('mime') != 'application/pdf' or
                result.get('sha256') != source_sha256):
            raise ValueError('The selected PDF does not match the current Drive version. Open the latest file and try again.')
    elif not body or len(body) > 4000:
        raise ValueError('Write a page note of up to 4000 characters.')
    with transaction(conn):
        user, doc = documents.check(conn, user, document_id, revision)
        documents.require(_allowed(conn, user, doc))
        current = rows(conn, 'SELECT fingerprint FROM document_file_version WHERE id=? AND document_id=?',
                       (version_id, document_id))
        if not current or current[0]['fingerprint'] != file_version['fingerprint']:
            raise documents.Conflict('The selected file version changed. Reload before saving.')
        if ink and not file_version['fingerprint']:
            if file_version['role'] != 'reference':
                raise ValueError('This draft has no confirmed Drive version. Attach it again.')
            conn.execute('UPDATE document_file_version SET fingerprint=? WHERE id=?',
                         (result['fingerprint'], version_id))
        if doc['status'] in ('closed', 'cancelled', 'released', 'awaiting_acknowledgment'):
            raise ValueError('Annotations are read-only after release or closure.')
        aid = conn.execute('''INSERT INTO document_annotation
            (document_id,version_id,actor_id,page_number,kind,body,strokes_json,source_sha256,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (document_id, version_id, user['id'], page, 'ink' if ink else 'note',
             body, json.dumps(strokes if ink else []), source_sha256 if ink else None,
             tzutil.now_iso())).lastrowid
        documents.finish(conn, user, doc, 'page_annotation',
                         {'annotation_id': aid, 'version_id': version_id, 'page': page, 'kind': 'ink' if ink else 'note'})
        return aid
