"""Additive shared-work foundation. Official document records remain authoritative."""


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS work_case (
      id INTEGER PRIMARY KEY,
      title TEXT NOT NULL, outcome TEXT NOT NULL,
      unit_id INTEGER NOT NULL REFERENCES org_unit(id),
      creator_id INTEGER NOT NULL REFERENCES admin_user(id),
      proposed_lead_id INTEGER REFERENCES admin_user(id),
      lead_id INTEGER REFERENCES admin_user(id),
      due_date TEXT, revision INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_case_creator ON work_case(creator_id,id);
    CREATE INDEX IF NOT EXISTS work_case_lead ON work_case(lead_id,id);
    CREATE INDEX IF NOT EXISTS work_case_unit ON work_case(unit_id,id);
    CREATE TABLE IF NOT EXISTS work_document (
      case_id INTEGER NOT NULL REFERENCES work_case(id),
      document_id INTEGER NOT NULL REFERENCES document(id),
      kind TEXT NOT NULL CHECK(kind='reference'),
      linked_by INTEGER NOT NULL REFERENCES admin_user(id),
      created_at TEXT NOT NULL,
      PRIMARY KEY(case_id,document_id));
    CREATE INDEX IF NOT EXISTS work_document_document ON work_document(document_id,case_id);
    CREATE TABLE IF NOT EXISTS work_task (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      title TEXT NOT NULL, expected_output TEXT NOT NULL,
      unit_id INTEGER NOT NULL REFERENCES org_unit(id),
      proposed_owner_id INTEGER REFERENCES admin_user(id), owner_id INTEGER REFERENCES admin_user(id),
      creator_id INTEGER NOT NULL REFERENCES admin_user(id),
      status TEXT NOT NULL CHECK(status IN ('proposed','todo','in_progress','for_review','done','cancelled')),
      due_date TEXT, submission TEXT NOT NULL DEFAULT '',
      revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_task_case ON work_task(case_id,id);
    CREATE INDEX IF NOT EXISTS work_task_owner ON work_task(owner_id,case_id);
    CREATE TABLE IF NOT EXISTS work_event (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), action TEXT NOT NULL,
      detail_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS work_event_no_update BEFORE UPDATE ON work_event
      BEGIN SELECT RAISE(ABORT,'Work history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS work_event_no_delete BEFORE DELETE ON work_event
      BEGIN SELECT RAISE(ABORT,'Work history is append-only'); END;
    ''')
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_comment (
      id INTEGER PRIMARY KEY,
      case_id INTEGER NOT NULL REFERENCES work_case(id),
      task_id INTEGER REFERENCES work_task(id),
      parent_id INTEGER REFERENCES work_comment(id),
      author_id INTEGER NOT NULL REFERENCES admin_user(id),
      created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_comment_thread ON work_comment(case_id,task_id,id);
    CREATE TABLE IF NOT EXISTS work_comment_revision (
      comment_id INTEGER NOT NULL REFERENCES work_comment(id),
      revision INTEGER NOT NULL CHECK(revision > 0),
      body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 4000),
      created_at TEXT NOT NULL,
      PRIMARY KEY(comment_id,revision));
    CREATE TRIGGER IF NOT EXISTS work_comment_no_update BEFORE UPDATE ON work_comment
      BEGIN SELECT RAISE(ABORT,'Discussion history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS work_comment_no_delete BEFORE DELETE ON work_comment
      BEGIN SELECT RAISE(ABORT,'Discussion history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS work_comment_revision_no_update BEFORE UPDATE ON work_comment_revision
      BEGIN SELECT RAISE(ABORT,'Discussion history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS work_comment_revision_no_delete BEFORE DELETE ON work_comment_revision
      BEGIN SELECT RAISE(ABORT,'Discussion history is append-only'); END;
    """)
    if 'mandatory' not in {r[1] for r in conn.execute('PRAGMA table_info(work_task)')}:
        conn.execute('ALTER TABLE work_task ADD COLUMN mandatory INTEGER NOT NULL DEFAULT 1 CHECK(mandatory IN (0,1))')
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_legacy_document (
      document_id INTEGER PRIMARY KEY REFERENCES document(id),
      case_id INTEGER NOT NULL UNIQUE REFERENCES work_case(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), reason TEXT NOT NULL,
      source_revision INTEGER NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS work_legacy_assignment (
      assignment_id INTEGER PRIMARY KEY REFERENCES document_assignment(id),
      case_id INTEGER NOT NULL REFERENCES work_case(id),
      task_id INTEGER UNIQUE REFERENCES work_task(id), source_json TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS work_legacy_assignment_no_update BEFORE UPDATE ON work_legacy_assignment
      BEGIN SELECT RAISE(ABORT,'Assignment mapping is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS work_legacy_assignment_no_delete BEFORE DELETE ON work_legacy_assignment
      BEGIN SELECT RAISE(ABORT,'Assignment mapping is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS work_legacy_document_no_update BEFORE UPDATE ON work_legacy_document
      BEGIN SELECT RAISE(ABORT,'Document mapping is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS work_legacy_document_no_delete BEFORE DELETE ON work_legacy_document
      BEGIN SELECT RAISE(ABORT,'Document mapping is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS migrated_assignment_no_update BEFORE UPDATE ON document_assignment
      WHEN EXISTS(SELECT 1 FROM work_legacy_document WHERE document_id IN (OLD.document_id,NEW.document_id))
      BEGIN SELECT RAISE(ABORT,'Use the shared task service for migrated assignments'); END;
    CREATE TRIGGER IF NOT EXISTS migrated_assignment_no_delete BEFORE DELETE ON document_assignment
      WHEN EXISTS(SELECT 1 FROM work_legacy_document WHERE document_id=OLD.document_id)
      BEGIN SELECT RAISE(ABORT,'Migrated assignment history is retained'); END;
    CREATE TRIGGER IF NOT EXISTS migrated_assignment_no_insert BEFORE INSERT ON document_assignment
      WHEN EXISTS(SELECT 1 FROM work_legacy_document WHERE document_id=NEW.document_id)
      BEGIN SELECT RAISE(ABORT,'Create contributions in Shared work'); END;
    CREATE VIEW IF NOT EXISTS document_assignment_effective AS
      SELECT a.* FROM document_assignment a
      WHERE NOT EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=a.document_id)
      UNION ALL
      SELECT COALESCE(m.assignment_id,-t.id),d.document_id,COALESCE(t.owner_id,t.proposed_owner_id),
        'contributor',t.expected_output,
        CASE t.status WHEN 'todo' THEN 'assigned' WHEN 'for_review' THEN 'submitted'
                      WHEN 'done' THEN 'completed' WHEN 'cancelled' THEN 'superseded' ELSE t.status END,
        t.due_date,t.submission,t.mandatory,t.created_at
      FROM work_task t JOIN work_legacy_document d ON d.case_id=t.case_id
      LEFT JOIN work_legacy_assignment m ON m.task_id=t.id;
    """)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_follow (
      case_id INTEGER NOT NULL REFERENCES work_case(id),
      user_id INTEGER NOT NULL REFERENCES admin_user(id),
      task_id INTEGER REFERENCES work_task(id), created_at TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS work_follow_scope ON work_follow(case_id,user_id,COALESCE(task_id,0));
    CREATE TABLE IF NOT EXISTS work_mention (
      comment_id INTEGER NOT NULL, revision INTEGER NOT NULL,
      user_id INTEGER NOT NULL REFERENCES admin_user(id),
      PRIMARY KEY(comment_id,revision,user_id),
      FOREIGN KEY(comment_id,revision) REFERENCES work_comment_revision(comment_id,revision));
    CREATE TABLE IF NOT EXISTS work_comment_read (
      comment_id INTEGER NOT NULL REFERENCES work_comment(id),
      user_id INTEGER NOT NULL REFERENCES admin_user(id), revision INTEGER NOT NULL,
      PRIMARY KEY(comment_id,user_id));
    CREATE TABLE IF NOT EXISTS work_notice (
      id INTEGER PRIMARY KEY, comment_id INTEGER NOT NULL REFERENCES work_comment(id),
      user_id INTEGER NOT NULL REFERENCES admin_user(id), revision INTEGER NOT NULL,
      reason TEXT NOT NULL CHECK(reason IN ('mention','reply','following')),
      created_at TEXT NOT NULL, UNIQUE(comment_id,user_id));
    CREATE INDEX IF NOT EXISTS work_notice_user ON work_notice(user_id,id);
    CREATE TRIGGER IF NOT EXISTS work_mention_no_update BEFORE UPDATE ON work_mention
      BEGIN SELECT RAISE(ABORT,'Mention history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS work_mention_no_delete BEFORE DELETE ON work_mention
      BEGIN SELECT RAISE(ABORT,'Mention history is append-only'); END;
    """)
    task_columns = {r[1] for r in conn.execute('PRAGMA table_info(work_task)')}
    for name, definition in (
        ('blocker_reason', "TEXT NOT NULL DEFAULT ''"),
        ('blocker_owner_id', 'INTEGER REFERENCES admin_user(id)'),
        ('blocker_due_date', 'TEXT')):
        if name not in task_columns:
            conn.execute('ALTER TABLE work_task ADD COLUMN ' + name + ' ' + definition)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_dependency (
      task_id INTEGER NOT NULL REFERENCES work_task(id),
      prerequisite_id INTEGER NOT NULL REFERENCES work_task(id),
      created_by INTEGER NOT NULL REFERENCES admin_user(id), created_at TEXT NOT NULL,
      PRIMARY KEY(task_id,prerequisite_id), CHECK(task_id<>prerequisite_id));
    CREATE INDEX IF NOT EXISTS work_dependency_upstream ON work_dependency(prerequisite_id,task_id);
    """)
    conn.execute("INSERT OR IGNORE INTO app_setting(key,value) VALUES ('work.enabled','0')")
    conn.commit()
