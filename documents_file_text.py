"""Explicit, version-bound indexing of Drive text for permitted documents."""
import uuid
import tzutil
import documents as documents
import documents_permissions as permissions
from documents_storage import rows, transaction, event


def index(conn, user, document_id, version_id, revision, adapter=None):
    user = permissions.actor(conn, user)
    doc = documents.get(conn, user, document_id)
    documents.writable(conn)
    documents.require(permissions.can_work(conn, user, doc))
    found = rows(conn, 'SELECT * FROM document_file_version WHERE id=? AND document_id=?',
                 (version_id, document_id))
    if not found:
        raise ValueError('Choose a file version on this document.')
    file_version = found[0]
    filing = conn.execute('''SELECT filing_state FROM document_intake
        WHERE document_id=? AND file_id=? ORDER BY id DESC LIMIT 1''',
        (document_id, file_version['file_id'])).fetchone()
    if filing and filing[0] not in ('complete', 'none'):
        raise ValueError('Wait for Drive filing to finish before indexing this file.')
    if not (file_version['id'] == doc['current_version'] or
            (doc['current_version'] is None and file_version['role'] == 'reference')):
        raise ValueError('Index the current draft or a reference file on a document without a current draft.')
    if adapter is None:
        from documents_operations import get_adapter
        adapter = get_adapter()
    fingerprint = file_version['fingerprint']
    if not fingerprint:
        if file_version['role'] != 'reference':
            raise ValueError('This draft has no confirmed Drive version. Attach it again.')
        inspected = adapter.call('inspect', {'file_id': file_version['file_id'],
                                  'actor_id': user['id'], 'max_bytes': 20 * 1024 * 1024}, str(uuid.uuid4()))
        if inspected.get('accessible') is not True or inspected.get('file_id') != file_version['file_id'] or not inspected.get('fingerprint'):
            raise ValueError('The relay could not confirm this reference file.')
        fingerprint = inspected['fingerprint']
    result = adapter.call('text', {'file_id': file_version['file_id'],
                          'fingerprint': fingerprint,
                          'actor_id': user['id']}, str(uuid.uuid4()))
    text = result.get('text')
    if (result.get('state') != 'confirmed' or result.get('file_id') != file_version['file_id'] or
            result.get('fingerprint') != fingerprint or
            not isinstance(text, str) or not text.strip() or len(text) > 100000):
        raise ValueError('The relay did not confirm searchable text for this exact file version.')
    with transaction(conn):
        user, doc = documents.check(conn, user, document_id, revision)
        documents.require(permissions.can_work(conn, user, doc))
        current = rows(conn, 'SELECT fingerprint FROM document_file_version WHERE id=? AND document_id=?',
                       (version_id, document_id))
        if not current or current[0]['fingerprint'] != file_version['fingerprint']:
            raise documents.Conflict('The file version changed. Reload before indexing.')
        if not file_version['fingerprint']:
            conn.execute('UPDATE document_file_version SET fingerprint=? WHERE id=?', (fingerprint, version_id))
        conn.execute("DELETE FROM document_search_fts WHERE source_type='file' AND source_id=?", (version_id,))
        conn.execute('INSERT INTO document_search_fts(document_id,source_type,source_id,body) VALUES (?,\'file\',?,?)',
                     (document_id, version_id, text))
        conn.execute('''INSERT INTO document_file_index(version_id,document_id,fingerprint,indexed_by,indexed_at,chars)
            VALUES (?,?,?,?,?,?) ON CONFLICT(version_id) DO UPDATE SET
              fingerprint=excluded.fingerprint,indexed_by=excluded.indexed_by,
              indexed_at=excluded.indexed_at,chars=excluded.chars''',
            (version_id, document_id, fingerprint, user['id'], tzutil.now_iso(), len(text)))
        event(conn, document_id, user, 'file_text_indexed',
              {'version_id': version_id, 'fingerprint': fingerprint, 'chars': len(text)})
    return len(text)


def remove(conn, user, document_id, version_id, revision):
    with transaction(conn):
        user, doc = documents.check(conn, user, document_id, revision)
        documents.require(permissions.can_work(conn, user, doc))
        if not conn.execute('SELECT 1 FROM document_file_index WHERE version_id=? AND document_id=?',
                            (version_id, document_id)).fetchone():
            raise ValueError('This file has no indexed text to remove.')
        conn.execute("DELETE FROM document_search_fts WHERE source_type='file' AND source_id=?", (version_id,))
        conn.execute('DELETE FROM document_file_index WHERE version_id=? AND document_id=?',
                     (version_id, document_id))
        event(conn, document_id, user, 'file_text_removed', {'version_id': version_id})
