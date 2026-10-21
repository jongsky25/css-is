"""Additive Supplies foundation and explicit transaction ownership."""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
from uuid import UUID

import storage as st
import tzutil as tz


class Invalid(ValueError):
    pass


class Denied(ValueError):
    pass


class Missing(Denied):
    pass


class Conflict(ValueError):
    pass


class Disabled(Conflict):
    pass


def rows(conn, sql, args=()):
    cursor = conn.execute(sql, args)
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, r)) for r in cursor.fetchall()]


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS supply_role_grant (
      id INTEGER PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES admin_user(id),
      role TEXT NOT NULL CHECK(role IN ('custodian','request_approver','replenishment_approver','auditor')),
      unit_id INTEGER REFERENCES org_unit(id),
      granted_by INTEGER NOT NULL REFERENCES admin_user(id),
      created_at TEXT NOT NULL,
      revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
      revoked_by INTEGER REFERENCES admin_user(id), revoked_at TEXT,
      CHECK((role='request_approver' AND unit_id IS NOT NULL) OR
            (role<>'request_approver' AND unit_id IS NULL)),
      CHECK((revoked_by IS NULL) = (revoked_at IS NULL)));
    CREATE UNIQUE INDEX IF NOT EXISTS supply_grant_active_scope
      ON supply_role_grant(user_id,role,COALESCE(unit_id,0)) WHERE revoked_at IS NULL;
    CREATE TABLE IF NOT EXISTS supply_item (
      id INTEGER PRIMARY KEY,
      code TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(code)) BETWEEN 1 AND 40),
      description TEXT NOT NULL CHECK(length(trim(description)) BETWEEN 1 AND 240),
      unit TEXT NOT NULL CHECK(length(trim(unit)) BETWEEN 1 AND 40),
      critical_level INTEGER NOT NULL DEFAULT 0
        CHECK(typeof(critical_level)='integer' AND critical_level BETWEEN 0 AND 2147483647),
      target_level INTEGER CHECK(target_level IS NULL OR
        (typeof(target_level)='integer' AND target_level BETWEEN critical_level AND 2147483647)),
      active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
      revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
      created_by INTEGER NOT NULL REFERENCES admin_user(id),
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS supply_item_catalog ON supply_item(active,code);
    CREATE TABLE IF NOT EXISTS supply_operation (
      operation_key TEXT PRIMARY KEY,
      actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      action TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
      result_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS supply_event (
      id INTEGER PRIMARY KEY,
      entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL,
      action TEXT NOT NULL, actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      detail_json TEXT NOT NULL, created_at TEXT NOT NULL,
      operation_key TEXT NOT NULL REFERENCES supply_operation(operation_key));
    CREATE INDEX IF NOT EXISTS supply_event_entity ON supply_event(entity_type,entity_id,id);
    CREATE TABLE IF NOT EXISTS supply_sequence (
      kind TEXT NOT NULL CHECK(kind IN ('SUP','REP','ISS')), year INTEGER NOT NULL,
      last_value INTEGER NOT NULL CHECK(last_value BETWEEN 0 AND 99999),
      PRIMARY KEY(kind,year));
    CREATE TRIGGER IF NOT EXISTS supply_event_no_update BEFORE UPDATE ON supply_event
      BEGIN SELECT RAISE(ABORT,'Supplies history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS supply_event_no_delete BEFORE DELETE ON supply_event
      BEGIN SELECT RAISE(ABORT,'Supplies history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS supply_operation_no_update BEFORE UPDATE ON supply_operation
      BEGIN SELECT RAISE(ABORT,'Supplies operations are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_operation_no_delete BEFORE DELETE ON supply_operation
      BEGIN SELECT RAISE(ABORT,'Supplies operations are immutable'); END;
    CREATE TABLE IF NOT EXISTS supply_receipt (
      id INTEGER PRIMARY KEY,
      supplier TEXT NOT NULL CHECK(length(trim(supplier)) BETWEEN 1 AND 240),
      dr_number TEXT NOT NULL DEFAULT '', apr_number TEXT NOT NULL DEFAULT '',
      procurement_mode TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
      effective_date TEXT NOT NULL,
      received_by INTEGER NOT NULL REFERENCES admin_user(id),
      recipient_snapshot TEXT NOT NULL, posted_at TEXT NOT NULL,
      operation_key TEXT NOT NULL UNIQUE REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED);
    CREATE TABLE IF NOT EXISTS supply_receipt_line (
      id INTEGER PRIMARY KEY, receipt_id INTEGER NOT NULL REFERENCES supply_receipt(id),
      item_id INTEGER NOT NULL REFERENCES supply_item(id),
      accepted_quantity INTEGER NOT NULL CHECK(typeof(accepted_quantity)='integer' AND accepted_quantity BETWEEN 1 AND 2147483647),
      unit_cost TEXT, expiry_date TEXT,
      code_snapshot TEXT NOT NULL, description_snapshot TEXT NOT NULL, unit_snapshot TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS supply_receipt_line_receipt ON supply_receipt_line(receipt_id,id);
    CREATE TABLE IF NOT EXISTS supply_stock_movement (
      id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES supply_item(id),
      kind TEXT NOT NULL CHECK(kind IN ('opening','receipt','issue','return','adjustment','reversal')),
      quantity_delta INTEGER NOT NULL CHECK(typeof(quantity_delta)='integer' AND quantity_delta BETWEEN -2147483647 AND 2147483647),
      effective_date TEXT NOT NULL, posted_at TEXT NOT NULL,
      posted_by INTEGER NOT NULL REFERENCES admin_user(id), actor_snapshot TEXT NOT NULL,
      source_type TEXT NOT NULL, source_id INTEGER NOT NULL, source_line_id INTEGER,
      receipt_line_id INTEGER UNIQUE REFERENCES supply_receipt_line(id),
      reverses_movement_id INTEGER REFERENCES supply_stock_movement(id),
      reason TEXT NOT NULL DEFAULT '',
      code_snapshot TEXT NOT NULL, description_snapshot TEXT NOT NULL, unit_snapshot TEXT NOT NULL,
      operation_key TEXT NOT NULL REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED,
      CHECK((kind='opening' AND quantity_delta>=0) OR
            (kind IN ('receipt','return') AND quantity_delta>0) OR
            (kind='issue' AND quantity_delta<0) OR
            (kind IN ('adjustment','reversal') AND quantity_delta<>0)),
      CHECK((kind='receipt' AND receipt_line_id IS NOT NULL AND source_type='receipt'
             AND source_line_id IS NOT NULL AND source_line_id=receipt_line_id) OR
            (kind<>'receipt' AND receipt_line_id IS NULL)));
    CREATE INDEX IF NOT EXISTS supply_stock_item_order ON supply_stock_movement(item_id,id);
    CREATE UNIQUE INDEX IF NOT EXISTS supply_stock_opening ON supply_stock_movement(item_id) WHERE kind='opening';
    CREATE TRIGGER IF NOT EXISTS supply_stock_opening_empty BEFORE INSERT ON supply_stock_movement
      WHEN NEW.kind='opening' AND EXISTS(SELECT 1 FROM supply_stock_movement WHERE item_id=NEW.item_id)
      BEGIN SELECT RAISE(ABORT,'An opening requires an empty item ledger'); END;
    CREATE TRIGGER IF NOT EXISTS supply_stock_receipt_match BEFORE INSERT ON supply_stock_movement
      WHEN NEW.kind='receipt' AND NOT EXISTS (
        SELECT 1 FROM supply_receipt_line l WHERE l.id=NEW.receipt_line_id AND l.item_id=NEW.item_id
          AND l.receipt_id=NEW.source_id AND l.accepted_quantity=NEW.quantity_delta)
      BEGIN SELECT RAISE(ABORT,'Receipt movement must match its accepted line'); END;
    CREATE TRIGGER IF NOT EXISTS supply_stock_no_update BEFORE UPDATE ON supply_stock_movement
      BEGIN SELECT RAISE(ABORT,'Stock movements are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_stock_no_delete BEFORE DELETE ON supply_stock_movement
      BEGIN SELECT RAISE(ABORT,'Stock movements are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_receipt_no_update BEFORE UPDATE ON supply_receipt
      BEGIN SELECT RAISE(ABORT,'Posted receipts are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_receipt_no_delete BEFORE DELETE ON supply_receipt
      BEGIN SELECT RAISE(ABORT,'Posted receipts are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_receipt_line_no_update BEFORE UPDATE ON supply_receipt_line
      BEGIN SELECT RAISE(ABORT,'Posted receipt lines are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_receipt_line_no_delete BEFORE DELETE ON supply_receipt_line
      BEGIN SELECT RAISE(ABORT,'Posted receipt lines are immutable'); END;
    CREATE TABLE IF NOT EXISTS supply_import_batch (
      id INTEGER PRIMARY KEY, source_sha256 TEXT NOT NULL, filename TEXT NOT NULL,
      sheet_count INTEGER NOT NULL, metadata_json TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'preview' CHECK(status IN ('preview','reviewed','applied')),
      revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
      created_by INTEGER NOT NULL REFERENCES admin_user(id), created_at TEXT NOT NULL,
      operation_key TEXT NOT NULL UNIQUE REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED);
    CREATE INDEX IF NOT EXISTS supply_import_hash ON supply_import_batch(source_sha256);
    CREATE TABLE IF NOT EXISTS supply_import_row (
      id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL REFERENCES supply_import_batch(id),
      source_sheet TEXT NOT NULL, source_row INTEGER NOT NULL, raw_json TEXT NOT NULL,
      UNIQUE(batch_id,source_sheet,source_row));
    CREATE TRIGGER IF NOT EXISTS supply_import_source_no_update BEFORE UPDATE OF
      source_sha256,filename,sheet_count,metadata_json,created_by,created_at,operation_key ON supply_import_batch
      BEGIN SELECT RAISE(ABORT,'Workbook source evidence is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_import_row_source_no_update BEFORE UPDATE OF
      batch_id,source_sheet,source_row,raw_json ON supply_import_row
      BEGIN SELECT RAISE(ABORT,'Workbook source evidence is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_import_no_delete BEFORE DELETE ON supply_import_batch
      BEGIN SELECT RAISE(ABORT,'Workbook source evidence is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_import_row_no_delete BEFORE DELETE ON supply_import_row
      BEGIN SELECT RAISE(ABORT,'Workbook source evidence is immutable'); END;
    ''')


    conn.executescript("""
    CREATE UNIQUE INDEX IF NOT EXISTS supply_import_applied_hash
      ON supply_import_batch(source_sha256) WHERE status='applied';
    CREATE TABLE IF NOT EXISTS supply_import_review (
      id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL REFERENCES supply_import_batch(id),
      row_id INTEGER REFERENCES supply_import_row(id), revision INTEGER NOT NULL,
      kind TEXT NOT NULL CHECK(kind IN ('decision','finalize','apply')),
      detail_json TEXT NOT NULL, actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      created_at TEXT NOT NULL,
      operation_key TEXT NOT NULL UNIQUE REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED,
      UNIQUE(batch_id,revision));
    CREATE INDEX IF NOT EXISTS supply_import_review_rows ON supply_import_review(batch_id,row_id,id);
    CREATE TRIGGER IF NOT EXISTS supply_import_review_no_update BEFORE UPDATE ON supply_import_review
      BEGIN SELECT RAISE(ABORT,'Import reviews are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_import_review_no_delete BEFORE DELETE ON supply_import_review
      BEGIN SELECT RAISE(ABORT,'Import reviews are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_import_applied_no_update BEFORE UPDATE ON supply_import_batch
      WHEN OLD.status='applied'
      BEGIN SELECT RAISE(ABORT,'Applied imports are immutable'); END;
    """)


    conn.executescript("""
    CREATE TABLE IF NOT EXISTS supply_request (
      id INTEGER PRIMARY KEY, control_number TEXT UNIQUE,
      requester_id INTEGER NOT NULL REFERENCES admin_user(id),
      requester_rp_id INTEGER NOT NULL REFERENCES resource_person(id),
      requester_snapshot TEXT NOT NULL, unit_id INTEGER NOT NULL REFERENCES org_unit(id),
      unit_snapshot TEXT NOT NULL, purpose TEXT NOT NULL, date_needed TEXT,
      approval_status TEXT NOT NULL DEFAULT 'draft'
        CHECK(approval_status IN ('draft','submitted','returned','approved','rejected','cancelled')),
      revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
      current_revision INTEGER NOT NULL DEFAULT 0 CHECK(current_revision>=0),
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, submitted_at TEXT);
    CREATE INDEX IF NOT EXISTS supply_request_owner ON supply_request(requester_id,id);
    CREATE TABLE IF NOT EXISTS supply_request_draft_line (
      id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES supply_request(id),
      item_id INTEGER NOT NULL REFERENCES supply_item(id),
      code_snapshot TEXT NOT NULL, description_snapshot TEXT NOT NULL, unit_snapshot TEXT NOT NULL,
      requested_quantity INTEGER NOT NULL CHECK(typeof(requested_quantity)='integer' AND requested_quantity BETWEEN 1 AND 2147483647),
      UNIQUE(request_id,item_id));
    CREATE INDEX IF NOT EXISTS supply_request_draft_item ON supply_request_draft_line(item_id,request_id);
    CREATE TABLE IF NOT EXISTS supply_request_revision (
      id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES supply_request(id),
      revision INTEGER NOT NULL CHECK(revision>0), purpose TEXT NOT NULL, date_needed TEXT,
      requester_rp_id INTEGER NOT NULL REFERENCES resource_person(id), requester_snapshot TEXT NOT NULL,
      unit_id INTEGER NOT NULL REFERENCES org_unit(id), unit_snapshot TEXT NOT NULL,
      submitted_at TEXT NOT NULL, submitted_by INTEGER NOT NULL REFERENCES admin_user(id),
      operation_key TEXT NOT NULL UNIQUE REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED,
      UNIQUE(request_id,revision));
    CREATE TABLE IF NOT EXISTS supply_request_revision_line (
      id INTEGER PRIMARY KEY, revision_id INTEGER NOT NULL REFERENCES supply_request_revision(id),
      line_id INTEGER NOT NULL REFERENCES supply_request_draft_line(id),
      item_id INTEGER NOT NULL REFERENCES supply_item(id),
      code_snapshot TEXT NOT NULL, description_snapshot TEXT NOT NULL, unit_snapshot TEXT NOT NULL,
      item_revision INTEGER NOT NULL,
      requested_quantity INTEGER NOT NULL CHECK(typeof(requested_quantity)='integer' AND requested_quantity BETWEEN 1 AND 2147483647),
      UNIQUE(revision_id,item_id), UNIQUE(revision_id,line_id));
    CREATE TRIGGER IF NOT EXISTS supply_request_revision_no_update BEFORE UPDATE ON supply_request_revision
      BEGIN SELECT RAISE(ABORT,'Submitted request revisions are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_request_revision_no_delete BEFORE DELETE ON supply_request_revision
      BEGIN SELECT RAISE(ABORT,'Submitted request revisions are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_request_revision_line_no_update BEFORE UPDATE ON supply_request_revision_line
      BEGIN SELECT RAISE(ABORT,'Submitted request lines are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_request_revision_line_no_delete BEFORE DELETE ON supply_request_revision_line
      BEGIN SELECT RAISE(ABORT,'Submitted request lines are immutable'); END;
    """)


    if 'active' not in {r[1] for r in conn.execute('PRAGMA table_info(supply_request_draft_line)')}:
        conn.execute('ALTER TABLE supply_request_draft_line ADD COLUMN active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))')
    conn.commit()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS supply_request_decision (
      id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES supply_request(id),
      revision_id INTEGER NOT NULL UNIQUE REFERENCES supply_request_revision(id),
      submitted_revision INTEGER NOT NULL,
      decision TEXT NOT NULL CHECK(decision IN ('approved','returned','rejected')),
      decided_by INTEGER NOT NULL REFERENCES admin_user(id), actor_snapshot TEXT NOT NULL,
      decided_at TEXT NOT NULL, reason TEXT NOT NULL,
      operation_key TEXT NOT NULL UNIQUE REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED,
      UNIQUE(request_id,submitted_revision));
    CREATE TABLE IF NOT EXISTS supply_request_decision_line (
      id INTEGER PRIMARY KEY, decision_id INTEGER NOT NULL REFERENCES supply_request_decision(id),
      revision_line_id INTEGER NOT NULL UNIQUE REFERENCES supply_request_revision_line(id),
      approved_quantity INTEGER NOT NULL CHECK(typeof(approved_quantity)='integer' AND approved_quantity BETWEEN 0 AND 2147483647),
      reason TEXT NOT NULL, UNIQUE(decision_id,revision_line_id));
    CREATE TABLE IF NOT EXISTS supply_reservation (
      id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES supply_request(id),
      line_id INTEGER NOT NULL REFERENCES supply_request_draft_line(id),
      revision_line_id INTEGER NOT NULL UNIQUE REFERENCES supply_request_revision_line(id),
      item_id INTEGER NOT NULL REFERENCES supply_item(id), approved_at TEXT NOT NULL,
      reserved_quantity INTEGER NOT NULL DEFAULT 0 CHECK(typeof(reserved_quantity)='integer' AND reserved_quantity BETWEEN 0 AND 2147483647),
      effective_issued_quantity INTEGER NOT NULL DEFAULT 0 CHECK(typeof(effective_issued_quantity)='integer' AND effective_issued_quantity>=0),
      cancelled_quantity INTEGER NOT NULL DEFAULT 0 CHECK(typeof(cancelled_quantity)='integer' AND cancelled_quantity>=0),
      version INTEGER NOT NULL DEFAULT 1 CHECK(version>0));
    CREATE INDEX IF NOT EXISTS supply_reservation_priority ON supply_reservation(item_id,approved_at,request_id,line_id);
    CREATE TRIGGER IF NOT EXISTS supply_decision_no_update BEFORE UPDATE ON supply_request_decision
      BEGIN SELECT RAISE(ABORT,'Request decisions are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_decision_no_delete BEFORE DELETE ON supply_request_decision
      BEGIN SELECT RAISE(ABORT,'Request decisions are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_decision_line_no_update BEFORE UPDATE ON supply_request_decision_line
      BEGIN SELECT RAISE(ABORT,'Decision lines are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_decision_line_no_delete BEFORE DELETE ON supply_request_decision_line
      BEGIN SELECT RAISE(ABORT,'Decision lines are immutable'); END;
    """)


    conn.executescript("""
    CREATE TABLE IF NOT EXISTS supply_request_cancellation (
      id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES supply_request(id),
      submitted_revision INTEGER NOT NULL, reason TEXT NOT NULL,
      cancelled_by INTEGER NOT NULL REFERENCES admin_user(id), actor_snapshot TEXT NOT NULL,
      cancelled_at TEXT NOT NULL,
      operation_key TEXT NOT NULL UNIQUE REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED);
    CREATE TABLE IF NOT EXISTS supply_request_cancellation_line (
      id INTEGER PRIMARY KEY, cancellation_id INTEGER NOT NULL REFERENCES supply_request_cancellation(id),
      reservation_id INTEGER NOT NULL REFERENCES supply_reservation(id),
      cancelled_quantity INTEGER NOT NULL CHECK(typeof(cancelled_quantity)='integer' AND cancelled_quantity BETWEEN 1 AND 2147483647),
      issued_quantity_snapshot INTEGER NOT NULL CHECK(issued_quantity_snapshot>=0),
      previous_reserved_quantity INTEGER NOT NULL CHECK(previous_reserved_quantity>=0),
      UNIQUE(cancellation_id,reservation_id));
    CREATE TRIGGER IF NOT EXISTS supply_cancellation_no_update BEFORE UPDATE ON supply_request_cancellation
      BEGIN SELECT RAISE(ABORT,'Cancellation evidence is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_cancellation_no_delete BEFORE DELETE ON supply_request_cancellation
      BEGIN SELECT RAISE(ABORT,'Cancellation evidence is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_cancellation_line_no_update BEFORE UPDATE ON supply_request_cancellation_line
      BEGIN SELECT RAISE(ABORT,'Cancellation evidence is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_cancellation_line_no_delete BEFORE DELETE ON supply_request_cancellation_line
      BEGIN SELECT RAISE(ABORT,'Cancellation evidence is immutable'); END;
    """)


    conn.executescript("""
    CREATE TABLE IF NOT EXISTS supply_issue (
      id INTEGER PRIMARY KEY, release_number TEXT NOT NULL UNIQUE,
      request_id INTEGER NOT NULL REFERENCES supply_request(id), submitted_revision INTEGER NOT NULL,
      recipient_id INTEGER NOT NULL REFERENCES admin_user(id), recipient_rp_id INTEGER NOT NULL REFERENCES resource_person(id),
      recipient_snapshot TEXT NOT NULL, recipient_unit_snapshot TEXT NOT NULL,
      alternate_reason TEXT NOT NULL, issued_by INTEGER NOT NULL REFERENCES admin_user(id),
      issuer_snapshot TEXT NOT NULL, effective_date TEXT NOT NULL, posted_at TEXT NOT NULL, note TEXT NOT NULL,
      operation_key TEXT NOT NULL UNIQUE REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED);
    CREATE INDEX IF NOT EXISTS supply_issue_request ON supply_issue(request_id,id);
    CREATE INDEX IF NOT EXISTS supply_issue_recipient ON supply_issue(recipient_id,id);
    CREATE TABLE IF NOT EXISTS supply_issue_line (
      id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES supply_issue(id),
      line_id INTEGER NOT NULL REFERENCES supply_request_draft_line(id),
      revision_line_id INTEGER NOT NULL REFERENCES supply_request_revision_line(id),
      reservation_id INTEGER NOT NULL REFERENCES supply_reservation(id), item_id INTEGER NOT NULL REFERENCES supply_item(id),
      issued_quantity INTEGER NOT NULL CHECK(typeof(issued_quantity)='integer' AND issued_quantity BETWEEN 1 AND 2147483647),
      code_snapshot TEXT NOT NULL, description_snapshot TEXT NOT NULL, unit_snapshot TEXT NOT NULL,
      movement_id INTEGER NOT NULL UNIQUE REFERENCES supply_stock_movement(id), UNIQUE(issue_id,line_id));
    CREATE TRIGGER IF NOT EXISTS supply_issue_line_match BEFORE INSERT ON supply_issue_line
      WHEN NOT EXISTS (SELECT 1 FROM supply_stock_movement m WHERE m.id=NEW.movement_id AND m.kind='issue'
        AND m.item_id=NEW.item_id AND m.quantity_delta=-NEW.issued_quantity AND m.source_type='issue'
        AND m.source_id=NEW.issue_id AND m.source_line_id=NEW.id)
      BEGIN SELECT RAISE(ABORT,'Issue line must match its stock movement'); END;
    CREATE TRIGGER IF NOT EXISTS supply_issue_no_update BEFORE UPDATE ON supply_issue
      BEGIN SELECT RAISE(ABORT,'Posted issues are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_issue_no_delete BEFORE DELETE ON supply_issue
      BEGIN SELECT RAISE(ABORT,'Posted issues are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_issue_line_no_update BEFORE UPDATE ON supply_issue_line
      BEGIN SELECT RAISE(ABORT,'Posted issue lines are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS supply_issue_line_no_delete BEFORE DELETE ON supply_issue_line
      BEGIN SELECT RAISE(ABORT,'Posted issue lines are immutable'); END;
    """)


    conn.executescript("""
    CREATE TABLE IF NOT EXISTS supply_issue_acknowledgment (
      id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES supply_issue(id),
      revision INTEGER NOT NULL CHECK(revision>0),
      status TEXT NOT NULL CHECK(status IN ('acknowledged','disputed')),
      method TEXT NOT NULL CHECK(method IN ('recipient','paper_recorded')),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), actor_snapshot TEXT NOT NULL,
      created_at TEXT NOT NULL, note TEXT NOT NULL, paper_reference TEXT, paper_received_date TEXT,
      operation_key TEXT NOT NULL UNIQUE REFERENCES supply_operation(operation_key) DEFERRABLE INITIALLY DEFERRED,
      UNIQUE(issue_id,revision),
      CHECK((method='recipient' AND paper_reference IS NULL AND paper_received_date IS NULL) OR
            (method='paper_recorded' AND status='acknowledged' AND length(trim(paper_reference))>0
             AND paper_received_date IS NOT NULL AND length(trim(note))>0)));
    CREATE INDEX IF NOT EXISTS supply_acknowledgment_issue ON supply_issue_acknowledgment(issue_id,revision);
    CREATE TRIGGER IF NOT EXISTS supply_acknowledgment_no_update BEFORE UPDATE ON supply_issue_acknowledgment
      BEGIN SELECT RAISE(ABORT,'Acknowledgment evidence is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS supply_acknowledgment_no_delete BEFORE DELETE ON supply_issue_acknowledgment
      BEGIN SELECT RAISE(ABORT,'Acknowledgment evidence is append-only'); END;
    """)


@contextmanager
def transaction(conn):
    if conn.in_transaction:
        raise RuntimeError('Supplies operations require a clean connection.')
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield
        conn.commit()
    except BaseException as exc:
        conn.rollback()
        if isinstance(exc, sqlite3.OperationalError) and ('locked' in str(exc) or 'busy' in str(exc)):
            raise Conflict('Supplies is busy. Retry the same form in a moment.') from exc
        raise


def operation(conn, user, key, action, payload):
    """Call after reloading current authority, before checking mutable revisions."""
    try:
        key = str(UUID(str(key)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise Invalid('Reload the form to obtain a valid operation key.') from exc
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    prior = rows(conn, 'SELECT * FROM supply_operation WHERE operation_key=?', (key,))
    if prior:
        prior = prior[0]
        if (prior['actor_id'], prior['action'], prior['payload_sha256']) != (user['id'], action, digest):
            raise Conflict('This form was already used for a different change. Reload it.')
        return key, digest, json.loads(prior['result_json'])
    return key, digest, None


def record(conn, user, key, digest, action, entity_type, result, detail):
    now = tz.now_iso()
    conn.execute('INSERT INTO supply_operation VALUES (?,?,?,?,?,?)',
                 (key, user['id'], action, digest, json.dumps(result, sort_keys=True), now))
    payload = json.dumps(detail, sort_keys=True)
    conn.execute('''INSERT INTO supply_event
      (entity_type,entity_id,action,actor_id,detail_json,created_at,operation_key) VALUES (?,?,?,?,?,?,?)''',
                 (entity_type, result['id'], action, user['id'], payload, now, key))
    st.audit(conn, user['username'], 'supply_' + action, target_type='supply_' + entity_type,
             target_id=result['id'], after=payload, commit=False)
    return result
