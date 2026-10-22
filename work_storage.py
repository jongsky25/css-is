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
    -- The task action and its recovery receipt commit in the same writer
    -- transaction. Keys belong to an actor, never to a browser session.
    CREATE TABLE IF NOT EXISTS work_api_operation (
      actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      operation_id TEXT NOT NULL,
      request_digest TEXT NOT NULL,
      case_id INTEGER NOT NULL REFERENCES work_case(id),
      task_id INTEGER NOT NULL REFERENCES work_task(id),
      result_revision INTEGER NOT NULL CHECK(result_revision > 0),
      completed_at TEXT NOT NULL,
      action TEXT NOT NULL DEFAULT 'acknowledge' CHECK(action IN ('acknowledge','submit')),
      PRIMARY KEY(actor_id,operation_id));
    CREATE TRIGGER IF NOT EXISTS work_api_operation_no_update BEFORE UPDATE ON work_api_operation
      BEGIN SELECT RAISE(ABORT,'API operation receipts are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS work_api_operation_no_delete BEFORE DELETE ON work_api_operation
      BEGIN SELECT RAISE(ABORT,'API operation receipts are retained'); END;
    CREATE TABLE IF NOT EXISTS work_event (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), action TEXT NOT NULL,
      detail_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS work_event_no_update BEFORE UPDATE ON work_event
      BEGIN SELECT RAISE(ABORT,'Work history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS work_event_no_delete BEFORE DELETE ON work_event
      BEGIN SELECT RAISE(ABORT,'Work history is append-only'); END;
    ''')
    if 'action' not in {r[1] for r in conn.execute('PRAGMA table_info(work_api_operation)')}:
        # The default identifies existing acknowledgements without rewriting
        # immutable rows or changing their original request digests.
        conn.execute("ALTER TABLE work_api_operation ADD COLUMN action TEXT NOT NULL DEFAULT 'acknowledge' CHECK(action IN ('acknowledge','submit'))")
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
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_task_source (
      task_id INTEGER PRIMARY KEY REFERENCES work_task(id),
      comment_id INTEGER NOT NULL UNIQUE REFERENCES work_comment(id), source_revision INTEGER NOT NULL,
      FOREIGN KEY(comment_id,source_revision) REFERENCES work_comment_revision(comment_id,revision));
    CREATE TABLE IF NOT EXISTS work_decision (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      comment_id INTEGER NOT NULL REFERENCES work_comment(id), source_revision INTEGER NOT NULL,
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), authority TEXT NOT NULL,
      kind TEXT NOT NULL CHECK(kind IN ('coordination','change')), body TEXT NOT NULL,
      supersedes_id INTEGER UNIQUE REFERENCES work_decision(id),
      document_id INTEGER REFERENCES document(id), document_revision INTEGER,
      document_version_id INTEGER REFERENCES document_file_version(id), created_at TEXT NOT NULL,
      UNIQUE(comment_id,source_revision),
      FOREIGN KEY(comment_id,source_revision) REFERENCES work_comment_revision(comment_id,revision));
    CREATE INDEX IF NOT EXISTS work_decision_case ON work_decision(case_id,id);
    CREATE TABLE IF NOT EXISTS work_decision_task (
      decision_id INTEGER NOT NULL REFERENCES work_decision(id),
      task_id INTEGER NOT NULL REFERENCES work_task(id), snapshot_json TEXT NOT NULL,
      PRIMARY KEY(decision_id,task_id));
    CREATE INDEX IF NOT EXISTS work_decision_task_task ON work_decision_task(task_id,decision_id);
    CREATE TABLE IF NOT EXISTS work_decision_resolution (
      decision_id INTEGER NOT NULL, task_id INTEGER NOT NULL,
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), reviewed_revision INTEGER NOT NULL,
      outcome TEXT NOT NULL CHECK(outcome IN ('retain','revise')), reason TEXT NOT NULL,
      created_at TEXT NOT NULL, PRIMARY KEY(decision_id,task_id),
      FOREIGN KEY(decision_id,task_id) REFERENCES work_decision_task(decision_id,task_id));
    """)
    for table in ('work_task_source','work_decision','work_decision_task','work_decision_resolution'):
        for action in ('UPDATE','DELETE'):
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} "
                         "BEGIN SELECT RAISE(ABORT,'Decision and source history is append-only'); END;")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_draft (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      title TEXT NOT NULL, url TEXT NOT NULL, file_id TEXT NOT NULL, kind TEXT NOT NULL,
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), reason TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_draft_case ON work_draft(case_id,id);
    CREATE TABLE IF NOT EXISTS work_support_file (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      title TEXT NOT NULL, url TEXT NOT NULL, file_id TEXT NOT NULL,
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_support_file_case ON work_support_file(case_id,id);
    CREATE TABLE IF NOT EXISTS work_support_retired (
      file_id INTEGER PRIMARY KEY REFERENCES work_support_file(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), reason TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS work_handoff (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      task_id INTEGER NOT NULL REFERENCES work_task(id), actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      note TEXT NOT NULL, task_snapshot_json TEXT NOT NULL,
      draft_id INTEGER REFERENCES work_draft(id), support_id INTEGER REFERENCES work_support_file(id),
      created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_handoff_case ON work_handoff(case_id,id);
    CREATE INDEX IF NOT EXISTS work_handoff_task ON work_handoff(task_id,id);
    """)
    for table in ('work_draft','work_support_file','work_support_retired','work_handoff'):
        for action in ('UPDATE','DELETE'):
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} "
                         "BEGIN SELECT RAISE(ABORT,'Draft and handoff history is append-only'); END;")
    if 'work_packet_id' not in {r[1] for r in conn.execute('PRAGMA table_info(document_review)')}:
        conn.execute('ALTER TABLE document_review ADD COLUMN work_packet_id INTEGER REFERENCES work_review_packet(id)')
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_review_packet (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      document_id INTEGER NOT NULL REFERENCES document(id),
      version_id INTEGER NOT NULL REFERENCES document_file_version(id),
      reviewer_id INTEGER NOT NULL REFERENCES admin_user(id), actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      snapshot_json TEXT NOT NULL, snapshot_hash TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_review_document ON work_review_packet(document_id,id);
    CREATE TABLE IF NOT EXISTS work_review_source (
      packet_id INTEGER NOT NULL REFERENCES work_review_packet(id), document_id INTEGER NOT NULL REFERENCES document(id),
      PRIMARY KEY(packet_id,document_id));
    CREATE INDEX IF NOT EXISTS work_review_source_document ON work_review_source(document_id,packet_id);
    CREATE TABLE IF NOT EXISTS work_review_invalidation (
      packet_id INTEGER PRIMARY KEY REFERENCES work_review_packet(id), actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      reason TEXT NOT NULL, created_at TEXT NOT NULL);
    """)
    for table in ('work_review_packet','work_review_source','work_review_invalidation'):
        for action in ('UPDATE','DELETE'):
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} "
                         "BEGIN SELECT RAISE(ABORT,'Consolidation review history is append-only'); END;")
    case_columns = {r[1] for r in conn.execute('PRAGMA table_info(work_case)')}
    for name, definition in (('status', "TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','completed'))"),
                             ('completion_mode', "TEXT NOT NULL DEFAULT 'undecided' CHECK(completion_mode IN ('undecided','internal','formal'))")):
        if name not in case_columns:
            conn.execute('ALTER TABLE work_case ADD COLUMN '+name+' '+definition)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_completion_requirement (
      case_id INTEGER NOT NULL REFERENCES work_case(id), document_id INTEGER NOT NULL REFERENCES document(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), reason TEXT NOT NULL, created_at TEXT NOT NULL,
      PRIMARY KEY(case_id,document_id));
    CREATE INDEX IF NOT EXISTS work_completion_document ON work_completion_requirement(document_id,case_id);
    CREATE TABLE IF NOT EXISTS work_completion (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id), actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      evidence TEXT NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_completion_case ON work_completion(case_id,id);
    """)
    for table in ('work_completion_requirement','work_completion'):
        for action in ('UPDATE','DELETE'):
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} "
                         "BEGIN SELECT RAISE(ABORT,'Completion evidence is append-only'); END;")
    conn.execute("INSERT OR IGNORE INTO app_setting(key,value) VALUES ('work.enabled','0')")
    conn.commit()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_notification_preference (
      user_id INTEGER PRIMARY KEY REFERENCES admin_user(id),
      routine_bell TEXT NOT NULL CHECK(routine_bell IN ('show','hide')),
      digest TEXT NOT NULL CHECK(digest IN ('off','daily','weekly')),
      revision INTEGER NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS work_digest (
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES admin_user(id),
      period_key TEXT NOT NULL, delivery_date TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('sending','sent','unknown','cancelled')),
      created_at TEXT NOT NULL, UNIQUE(user_id,period_key), UNIQUE(user_id,delivery_date));
    CREATE TABLE IF NOT EXISTS work_digest_notice (
      digest_id INTEGER NOT NULL REFERENCES work_digest(id),
      notice_id INTEGER PRIMARY KEY REFERENCES work_notice(id));
    CREATE INDEX IF NOT EXISTS work_digest_notice_batch ON work_digest_notice(digest_id);
    """)
