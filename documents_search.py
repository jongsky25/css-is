"""Search stored correspondence text; source files and transient OCR stay in Drive."""
import re
import unicodedata


SOURCES = (
    ('document', 'document', 'id', 'id', "{r}.number || ' ' || {r}.subject || ' ' || {r}.type || ' ' || {r}.sender"),
    ('reference', 'document_reference', 'id', 'document_id', "{r}.kind || ' ' || {r}.value"),
    ('receipt', 'document_receipt', 'id', 'document_id', "{r}.channel || ' ' || {r}.sender || ' ' || {r}.evidence"),
    ('instruction', 'document_directive', 'id', 'document_id', '{r}.text'),
    ('email_body', 'document_intake_email', 'id', 'document_id', '{r}.body_text'),
)


def install(conn):
    """Create the index once and keep it current through source-table triggers."""
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_search_fts'").fetchone()
    conn.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS document_search_fts USING fts5(
        document_id UNINDEXED, source_type UNINDEXED, source_id UNINDEXED, body,
        tokenize='unicode61 remove_diacritics 2')''')
    for kind, table, key, doc_id, body in SOURCES:
        insert = (f"INSERT INTO document_search_fts(document_id,source_type,source_id,body) "
                  f"SELECT NEW.{doc_id},'{kind}',NEW.{key},{body.format(r='NEW')} WHERE NEW.{doc_id} IS NOT NULL")
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS document_search_{kind}_insert
            AFTER INSERT ON {table} BEGIN {insert}; END''')
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS document_search_{kind}_update
            AFTER UPDATE ON {table} BEGIN
              DELETE FROM document_search_fts WHERE source_type='{kind}' AND source_id=OLD.{key};
              {insert};
            END''')
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS document_search_{kind}_delete
            AFTER DELETE ON {table} BEGIN
              DELETE FROM document_search_fts WHERE source_type='{kind}' AND source_id=OLD.{key};
            END''')
    if not exists:
        for kind, table, key, doc_id, body in SOURCES:
            conn.execute(f'''INSERT INTO document_search_fts(document_id,source_type,source_id,body)
                SELECT s.{doc_id},?,s.{key},{body.format(r='s')} FROM {table} s
                WHERE s.{doc_id} IS NOT NULL''', (kind,))


def _match_expression(query):
    query = unicodedata.normalize('NFKC', str(query or '')).strip()
    if len(query) > 120:
        return None
    terms = re.findall(r'\w+', query, flags=re.UNICODE)
    if not terms:
        return None
    if len(terms) > 8:
        return None
    return ' AND '.join('"' + term.replace('"', '""') + '"*' for term in terms)


def matches(conn, query):
    """Return candidate source text; callers must check document access first."""
    expression = _match_expression(query)
    if not expression:
        return {}
    found = {}
    for document_id, kind, body in conn.execute('''SELECT document_id,source_type,body
        FROM document_search_fts WHERE document_search_fts MATCH ? ORDER BY rank''', (expression,)):
        found.setdefault(int(document_id), (kind, body or ''))
    return found


def excerpt(body, query, width=180):
    body = ' '.join(str(body or '').split())
    if len(body) <= width:
        return body
    terms = re.findall(r'\w+', unicodedata.normalize('NFKC', query), flags=re.UNICODE)
    lowered = body.casefold()
    positions = [lowered.find(term.casefold()) for term in terms]
    start = max(0, min((p for p in positions if p >= 0), default=0) - 50)
    if start + width > len(body):
        start = max(0, len(body) - width)
    return ('…' if start else '') + body[start:start + width] + ('…' if start + width < len(body) else '')


LABELS = {'document': 'Record details', 'reference': 'Reference', 'receipt': 'Receipt',
          'instruction': 'Instruction', 'email_body': 'Email body'}
