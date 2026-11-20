"""Additive private advisory drafts; no import, worker or notification side effects."""


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS advisory_record (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL UNIQUE REFERENCES document(id),
      event_id INTEGER UNIQUE REFERENCES event(id), number TEXT NOT NULL UNIQUE,
      reservation_date TEXT NOT NULL, initiator_id INTEGER NOT NULL REFERENCES admin_user(id),
      unit_id INTEGER NOT NULL REFERENCES org_unit(id), current_revision INTEGER,
      created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS advisory_revision (
      id INTEGER PRIMARY KEY, advisory_id INTEGER NOT NULL REFERENCES advisory_record(id),
      ordinal INTEGER NOT NULL, version_id INTEGER NOT NULL UNIQUE REFERENCES document_file_version(id),
      payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, source_json TEXT NOT NULL,
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), created_at TEXT NOT NULL,
      summary TEXT NOT NULL, UNIQUE(advisory_id,ordinal));
    CREATE TABLE IF NOT EXISTS advisory_artifact (
      revision_id INTEGER NOT NULL REFERENCES advisory_revision(id), format TEXT NOT NULL CHECK(format IN ('pdf','png')),
      sha256 TEXT NOT NULL, data BLOB NOT NULL CHECK(length(data)<=5242880),
      PRIMARY KEY(revision_id,format));
    CREATE TABLE IF NOT EXISTS advisory_existing_public (
      advisory_id INTEGER NOT NULL REFERENCES advisory_record(id), format TEXT NOT NULL CHECK(format IN ('pdf','png')),
      data BLOB NOT NULL CHECK(length(data)<=5242880), sha256 TEXT NOT NULL, captured_at TEXT NOT NULL,
      PRIMARY KEY(advisory_id,format));
    CREATE TABLE IF NOT EXISTS advisory_save_request (
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), operation_key TEXT NOT NULL,
      event_id INTEGER NOT NULL REFERENCES event(id), payload_hash TEXT NOT NULL,
      advisory_id INTEGER NOT NULL REFERENCES advisory_record(id), revision_id INTEGER NOT NULL REFERENCES advisory_revision(id),
      PRIMARY KEY(actor_id,operation_key));
    ''')
    for table in ('advisory_revision', 'advisory_artifact', 'advisory_existing_public', 'advisory_save_request'):
        for operation in ('UPDATE', 'DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'Advisory history is immutable'); END''')
    columns = {r[1] for r in conn.execute('PRAGMA table_info(document_file_version)')}
    if 'backend' not in columns:
        conn.execute("ALTER TABLE document_file_version ADD COLUMN backend TEXT NOT NULL DEFAULT 'drive' CHECK(backend IN ('drive','advisory'))")

    for operation in ('UPDATE', 'DELETE'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS advisory_version_no_{operation.lower()}
            BEFORE {operation} ON document_file_version
            WHEN EXISTS (SELECT 1 FROM advisory_revision WHERE version_id=OLD.id)
            BEGIN SELECT RAISE(ABORT,'Saved advisory versions are immutable'); END''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS advisory_identity_no_update
        BEFORE UPDATE OF document_id,event_id,number,reservation_date,initiator_id ON advisory_record
        BEGIN SELECT RAISE(ABORT,'Advisory identity is immutable'); END''')
