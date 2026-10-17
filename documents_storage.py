"""Additive document registry schema. No binary files or extracted text are persisted."""
from contextlib import contextmanager
import json
import storage as st
import tzutil as tz


def rows(conn, sql, args=()):
    cur = conn.execute(sql, args)
    return [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS document_email_import (
      id INTEGER PRIMARY KEY, mailbox TEXT NOT NULL, message_id TEXT NOT NULL,
      payload_hash TEXT NOT NULL, document_id INTEGER NOT NULL REFERENCES document(id),
      received_at TEXT NOT NULL, attachments_json TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'registered' CHECK(status='registered'),
      created_at TEXT NOT NULL, UNIQUE(mailbox,message_id));
    CREATE INDEX IF NOT EXISTS document_email_import_document ON document_email_import(document_id);
    CREATE TABLE IF NOT EXISTS document_sequence (
      year INTEGER NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
      value INTEGER NOT NULL, PRIMARY KEY(year,direction));
    CREATE TABLE IF NOT EXISTS document (
      id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE,
      direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')), subject TEXT NOT NULL,
      type TEXT NOT NULL, sender TEXT NOT NULL DEFAULT '', document_date TEXT, received_at TEXT,
      creator_id INTEGER NOT NULL REFERENCES admin_user(id), unit_id INTEGER REFERENCES org_unit(id),
      lead_id INTEGER REFERENCES admin_user(id), verification TEXT NOT NULL DEFAULT 'pending',
      status TEXT NOT NULL, visibility TEXT NOT NULL DEFAULT 'preverification',
      priority TEXT NOT NULL DEFAULT 'normal', due_date TEXT, original_due_date TEXT,
      due_source TEXT, policy_json TEXT NOT NULL DEFAULT '{}', matches_json TEXT NOT NULL DEFAULT '[]',
      review_class TEXT, reviewer_id INTEGER REFERENCES admin_user(id),
      current_version INTEGER, approved_version INTEGER, signed_version INTEGER,
      reconcile INTEGER NOT NULL DEFAULT 0, canonical_id INTEGER REFERENCES document(id),
      revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS document_due ON document(status,due_date);
    CREATE TABLE IF NOT EXISTS document_role_grant (
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES admin_user(id),
      role TEXT NOT NULL CHECK(role IN ('records','workflow_admin','grant_admin','signatory')),
      unit_id INTEGER REFERENCES org_unit(id), granted_by INTEGER REFERENCES admin_user(id),
      created_at TEXT NOT NULL, revoked_at TEXT);
    CREATE TABLE IF NOT EXISTS document_access (
      document_id INTEGER NOT NULL REFERENCES document(id), user_id INTEGER NOT NULL REFERENCES admin_user(id),
      source TEXT NOT NULL, PRIMARY KEY(document_id,user_id,source));
    CREATE TABLE IF NOT EXISTS document_reference (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id), kind TEXT NOT NULL, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_receipt (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id), channel TEXT NOT NULL,
      sender TEXT NOT NULL, received_at TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS document_relation (
      source_id INTEGER NOT NULL REFERENCES document(id), target_id INTEGER NOT NULL REFERENCES document(id),
      kind TEXT NOT NULL, PRIMARY KEY(source_id,target_id,kind), CHECK(source_id<>target_id));
    CREATE TABLE IF NOT EXISTS document_assignment (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      user_id INTEGER NOT NULL REFERENCES admin_user(id), role TEXT NOT NULL, action TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'proposed', due_date TEXT, outcome TEXT NOT NULL DEFAULT '',
      mandatory INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_directive (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), text TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_file_version (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      url TEXT NOT NULL, file_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
      role TEXT NOT NULL, parent_id INTEGER REFERENCES document_file_version(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_review (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      version_id INTEGER NOT NULL REFERENCES document_file_version(id), actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      decision TEXT NOT NULL, reason TEXT NOT NULL, delegation_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_signature (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      version_id INTEGER NOT NULL REFERENCES document_file_version(id), signatory_id INTEGER NOT NULL REFERENCES admin_user(id),
      method TEXT NOT NULL, operation_id TEXT UNIQUE, evidence TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_event (
      id INTEGER PRIMARY KEY, document_id INTEGER REFERENCES document(id), actor_id INTEGER REFERENCES admin_user(id),
      action TEXT NOT NULL, detail_json TEXT NOT NULL, occurred_at TEXT NOT NULL, recorded_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS document_event_no_update BEFORE UPDATE ON document_event
      BEGIN SELECT RAISE(ABORT,'Document history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS document_event_no_delete BEFORE DELETE ON document_event
      BEGIN SELECT RAISE(ABORT,'Document history is append-only'); END;
    CREATE TABLE IF NOT EXISTS document_rule_version (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, family_id INTEGER, body_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
      revision INTEGER NOT NULL DEFAULT 1, actor_id INTEGER NOT NULL REFERENCES admin_user(id), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_notice (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      event_id INTEGER REFERENCES document_event(id), user_id INTEGER NOT NULL REFERENCES admin_user(id),
      kind TEXT NOT NULL, dedup_key TEXT NOT NULL UNIQUE, due_at TEXT NOT NULL,
      in_app INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
      error TEXT NOT NULL DEFAULT '', sent_at TEXT);
    CREATE TABLE IF NOT EXISTS document_job (
      id TEXT PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), kind TEXT NOT NULL,
      version_id INTEGER REFERENCES document_file_version(id), payload_json TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'pending', result_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_dispatch (
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
      version_id INTEGER NOT NULL REFERENCES document_file_version(id), operation_id TEXT NOT NULL UNIQUE,
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), channel TEXT NOT NULL, sender TEXT NOT NULL,
      evidence TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS document_dispatch_recipient (
      dispatch_id INTEGER NOT NULL REFERENCES document_dispatch(id), recipient TEXT NOT NULL,
      outcome TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '', acknowledged_at TEXT,
      PRIMARY KEY(dispatch_id,recipient));
    CREATE TABLE IF NOT EXISTS document_calendar (
      document_id INTEGER PRIMARY KEY REFERENCES document(id), entry_id INTEGER NOT NULL REFERENCES calendar_entry(id),
      confirmed_by INTEGER NOT NULL REFERENCES admin_user(id), confirmed_at TEXT NOT NULL);
    ''')
    columns={row[1] for row in conn.execute('PRAGMA table_info(document_rule_version)')}
    if 'family_id' not in columns:
        conn.execute('ALTER TABLE document_rule_version ADD COLUMN family_id INTEGER')
    for key in ('documents.enabled', 'documents.sending_enabled', 'documents.gmail_intake_enabled'):
        conn.execute('INSERT OR IGNORE INTO app_setting(key,value) VALUES (?,?)', (key, '0'))
    conn.commit()


@contextmanager
def transaction(conn):
    """Serialize writers before reading revisions/sequences. Never commit caller work."""
    if conn.in_transaction:
        raise RuntimeError('Document operations require a clean connection')
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def event(conn, doc_id, actor, action, detail):
    now = tz.now_iso()
    payload = json.dumps(detail, sort_keys=True)
    eid = conn.execute('INSERT INTO document_event(document_id,actor_id,action,detail_json,occurred_at,recorded_at) VALUES (?,?,?,?,?,?)',
                       (doc_id, actor['id'], action, payload, now, now)).lastrowid
    st.audit(conn, actor['username'], 'document_' + action, target_type='document', target_id=doc_id,
             after=payload, commit=False)
    return eid
