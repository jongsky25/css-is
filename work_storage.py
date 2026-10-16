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
    CREATE TABLE IF NOT EXISTS work_event (
      id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES work_case(id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id), action TEXT NOT NULL,
      detail_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS work_event_no_update BEFORE UPDATE ON work_event
      BEGIN SELECT RAISE(ABORT,'Work history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS work_event_no_delete BEFORE DELETE ON work_event
      BEGIN SELECT RAISE(ABORT,'Work history is append-only'); END;
    ''')
    conn.execute("INSERT OR IGNORE INTO app_setting(key,value) VALUES ('work.enabled','0')")
    conn.commit()
