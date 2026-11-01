"""Durable two-way Telegram storage. Business actions remain separately gated."""
import os


# Deliberately independent of Apprise's private discussion digest switch.
SWITCHES = (
    'inbound', 'delivery', 'link', 'groups', 'calendar_read', 'rooms_read',
    'calendar_create', 'calendar_reschedule', 'calendar_cancel', 'rooms_request', 'rooms_withdraw', 'rooms_move', 'change_notices', 'reminders', 'work_read', 'tasks_acknowledge', 'tasks_submit', 'tasks_create', 'tasks_deadline', 'tasks_accept', 'tasks_return', 'tasks_assign', 'tasks_reassign', 'tasks_reopen', 'tasks_cancel', 'tasks_review_read', 'tasks_blockers_read', 'documents_read', 'supplies_read', 'travel_read', 'meals_read', 'arrangements_read',
)


def enabled(capability):
    """Exact opt-in only; an unknown capability is a programming error."""
    if capability not in SWITCHES:
        raise ValueError('Unknown Telegram capability')
    return os.environ.get('CSS_TELEGRAM_' + capability.upper() + '_ENABLED', '0') == '1'


def install(conn):
    """Add empty tables, preserving existing data and all channel preferences."""
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS telegram_connection (
      id INTEGER PRIMARY KEY,
      account_id INTEGER NOT NULL REFERENCES admin_user(id),
      bot_identity INTEGER, bot_fingerprint TEXT,
      telegram_user_id INTEGER NOT NULL CHECK(telegram_user_id > 0),
      private_chat_id INTEGER NOT NULL CHECK(private_chat_id > 0),
      state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','active','paused','revoked')),
      generation TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revoked_at TEXT,
      CHECK((state='revoked') = (revoked_at IS NOT NULL)));
    CREATE UNIQUE INDEX IF NOT EXISTS telegram_account_live
      ON telegram_connection(account_id) WHERE revoked_at IS NULL;
    CREATE INDEX IF NOT EXISTS telegram_sender_history ON telegram_connection(telegram_user_id,id);
    CREATE UNIQUE INDEX IF NOT EXISTS telegram_sender_live
      ON telegram_connection(telegram_user_id) WHERE revoked_at IS NULL;

    CREATE TABLE IF NOT EXISTS telegram_update (
      id INTEGER PRIMARY KEY,
      bot_identity INTEGER NOT NULL CHECK(bot_identity > 0),
      update_id INTEGER NOT NULL CHECK(update_id >= 0),
      sender_id INTEGER, chat_id INTEGER, topic_id INTEGER,
      connection_id INTEGER REFERENCES telegram_connection(id), generation TEXT,
      payload_json TEXT, payload_hash TEXT NOT NULL,
      received_at TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'queued'
        CHECK(state IN ('queued','processing','processed','ignored','cancelled')),
      attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
      claim_token TEXT, lease_until TEXT, error_code TEXT,
      UNIQUE(bot_identity,update_id));
    CREATE INDEX IF NOT EXISTS telegram_update_queue ON telegram_update(state,lease_until,id);
    CREATE INDEX IF NOT EXISTS telegram_update_rate ON telegram_update(received_at);
    CREATE INDEX IF NOT EXISTS telegram_update_sender_rate ON telegram_update(sender_id,received_at);

    CREATE TABLE IF NOT EXISTS telegram_operation (
      operation_id TEXT PRIMARY KEY NOT NULL,
      actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      connection_id INTEGER NOT NULL REFERENCES telegram_connection(id),
      generation TEXT NOT NULL, action TEXT NOT NULL, client_key TEXT NOT NULL,
      input_hash TEXT NOT NULL, context_hash TEXT, context_json TEXT, target_id INTEGER, expected_revision TEXT,
      state TEXT NOT NULL DEFAULT 'pending'
        CHECK(state IN ('pending','committed','partial','failed','cancelled')),
      result_entry_id INTEGER REFERENCES calendar_entry(id),
      result_room_id INTEGER REFERENCES room_reservation(id), result_code TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(actor_id,client_key));

    CREATE TABLE IF NOT EXISTS telegram_delivery (
      id INTEGER PRIMARY KEY, dedupe_key TEXT NOT NULL UNIQUE,
      operation_id TEXT REFERENCES telegram_operation(operation_id), event_key TEXT,
      connection_id INTEGER REFERENCES telegram_connection(id), generation TEXT,
      chat_id INTEGER NOT NULL CHECK(chat_id != 0), topic_id INTEGER,
      registration_id INTEGER, registration_generation TEXT,
      projection_json TEXT NOT NULL DEFAULT '{}',
      state TEXT NOT NULL DEFAULT 'queued'
        CHECK(state IN ('queued','claimed','sending','retry_wait','accepted','failed','uncertain','cancelled')),
      attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
      claim_token TEXT, lease_until TEXT, retry_at TEXT, expires_at TEXT NOT NULL,
      provider_message_id INTEGER, error_code TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS telegram_delivery_queue ON telegram_delivery(state,retry_at,id);
    CREATE INDEX IF NOT EXISTS telegram_delivery_destination ON telegram_delivery(chat_id,state,updated_at);
    CREATE INDEX IF NOT EXISTS telegram_delivery_retention ON telegram_delivery(state,updated_at);
    CREATE TABLE IF NOT EXISTS telegram_link_challenge (
      id TEXT PRIMARY KEY NOT NULL, token_hash TEXT NOT NULL UNIQUE, confirm_hash TEXT NOT NULL UNIQUE,
      telegram_user_id INTEGER NOT NULL, private_chat_id INTEGER NOT NULL,
      bot_identity INTEGER NOT NULL, bot_fingerprint TEXT NOT NULL,
      account_id INTEGER REFERENCES admin_user(id), session_id TEXT,
      scopes_json TEXT NOT NULL DEFAULT '[]',
      state TEXT NOT NULL CHECK(state IN ('issued','claimed','confirmed','cancelled')),
      created_at TEXT NOT NULL, expires_at TEXT NOT NULL, claimed_at TEXT, consumed_at TEXT);
    CREATE INDEX IF NOT EXISTS telegram_challenge_sender ON telegram_link_challenge(telegram_user_id,state);
    CREATE INDEX IF NOT EXISTS telegram_challenge_account ON telegram_link_challenge(account_id,state);
    CREATE TABLE IF NOT EXISTS telegram_grant (
      id INTEGER PRIMARY KEY, connection_id INTEGER NOT NULL REFERENCES telegram_connection(id),
      account_id INTEGER NOT NULL REFERENCES admin_user(id), action TEXT NOT NULL,
      generation TEXT NOT NULL, bot_identity INTEGER NOT NULL, bot_fingerprint TEXT NOT NULL,
      consented_at TEXT NOT NULL, revoked_at TEXT,
      UNIQUE(connection_id,action,generation));
    CREATE TABLE IF NOT EXISTS telegram_group_request (
      id TEXT PRIMARY KEY NOT NULL, update_id INTEGER NOT NULL,
      account_id INTEGER NOT NULL REFERENCES admin_user(id),
      connection_id INTEGER NOT NULL REFERENCES telegram_connection(id), connection_generation TEXT NOT NULL,
      chat_id INTEGER NOT NULL CHECK(chat_id<0), topic_id INTEGER NOT NULL DEFAULT 0 CHECK(topic_id>=0),
      bot_identity INTEGER NOT NULL, bot_fingerprint TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('observed','consumed','cancelled')),
      created_at TEXT NOT NULL, expires_at TEXT NOT NULL, UNIQUE(bot_identity,update_id));
    CREATE INDEX IF NOT EXISTS telegram_group_request_owner ON telegram_group_request(account_id,state,expires_at);
    CREATE TABLE IF NOT EXISTS telegram_group (
      id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL CHECK(chat_id<0),
      topic_id INTEGER NOT NULL DEFAULT 0 CHECK(topic_id>=0),
      owner_account_id INTEGER NOT NULL REFERENCES admin_user(id),
      owner_connection_id INTEGER NOT NULL REFERENCES telegram_connection(id), owner_generation TEXT NOT NULL,
      bot_identity INTEGER NOT NULL, bot_fingerprint TEXT NOT NULL,
      purpose TEXT NOT NULL CHECK(length(purpose) BETWEEN 1 AND 200), policy_version TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('active','paused','revoked')),
      generation TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))), reason TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, consented_at TEXT NOT NULL,
      UNIQUE(chat_id,topic_id));
    CREATE INDEX IF NOT EXISTS telegram_group_owner ON telegram_group(owner_connection_id,state);
    CREATE TABLE IF NOT EXISTS telegram_group_share (
      entry_id INTEGER NOT NULL REFERENCES calendar_entry(id) ON DELETE CASCADE,
      registration_id INTEGER NOT NULL REFERENCES telegram_group(id),
      registration_generation TEXT NOT NULL,
      revision TEXT NOT NULL, consented_by INTEGER NOT NULL REFERENCES admin_user(id),
      consented_at TEXT NOT NULL, revoked_at TEXT,
      PRIMARY KEY(entry_id,registration_id));
    CREATE INDEX IF NOT EXISTS telegram_share_registration ON telegram_group_share(registration_id,revoked_at);
    CREATE TRIGGER IF NOT EXISTS telegram_share_fence AFTER UPDATE ON telegram_group_share
    BEGIN
      UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,error_code='share_changed'
        WHERE registration_id=NEW.registration_id AND state IN ('queued','claimed','retry_wait','sending');
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_share_delete_fence BEFORE DELETE ON telegram_group_share
    BEGIN
      UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,error_code='share_changed'
        WHERE registration_id=OLD.registration_id AND state IN ('queued','claimed','retry_wait','sending');
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_calendar_share_changed AFTER UPDATE ON calendar_entry
    BEGIN
      UPDATE telegram_group_share SET revoked_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE entry_id=NEW.id AND revoked_at IS NULL;
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_group_fence AFTER UPDATE OF state,generation ON telegram_group
    WHEN OLD.state IS NOT NEW.state OR OLD.generation IS NOT NEW.generation
    BEGIN
      UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,projection_json='{}',error_code='group_changed',
        updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE registration_id=NEW.id AND state IN ('queued','claimed','retry_wait','sending');
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_connection_groups AFTER UPDATE OF state,generation ON telegram_connection
    WHEN OLD.state IS NOT NEW.state OR OLD.generation IS NOT NEW.generation
    BEGIN
      UPDATE telegram_group SET state='paused',generation=lower(hex(randomblob(16))),reason='connection_changed',
        updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE owner_connection_id=NEW.id AND state<>'revoked';
      UPDATE telegram_group_request SET state='cancelled' WHERE connection_id=NEW.id AND state='observed';
      UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,projection_json='{}',error_code='connection_changed',
        updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE connection_id=NEW.id AND chat_id<0 AND state IN ('queued','claimed','retry_wait','sending');
    END;
    CREATE TABLE IF NOT EXISTS telegram_preview (
      token_hash TEXT PRIMARY KEY NOT NULL,
      operation_id TEXT NOT NULL UNIQUE REFERENCES telegram_operation(operation_id),
      actor_id INTEGER NOT NULL REFERENCES admin_user(id),
      connection_id INTEGER NOT NULL REFERENCES telegram_connection(id), generation TEXT NOT NULL,
      bot_identity INTEGER NOT NULL, bot_fingerprint TEXT NOT NULL,
      chat_id INTEGER NOT NULL, topic_id INTEGER,
      registration_id INTEGER REFERENCES telegram_group(id), registration_generation TEXT,
      action TEXT NOT NULL, input_hash TEXT NOT NULL,
      fields_json TEXT, summary_json TEXT, expected_json TEXT, token_nonce TEXT,
      state TEXT NOT NULL CHECK(state IN ('pending','consumed','cancelled')),
      created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT);
    CREATE INDEX IF NOT EXISTS telegram_preview_expiry ON telegram_preview(state,expires_at);
    CREATE TABLE IF NOT EXISTS telegram_meeting_origin (
      id TEXT PRIMARY KEY NOT NULL, action TEXT NOT NULL DEFAULT 'calendar.create', account_id INTEGER NOT NULL REFERENCES admin_user(id),
      connection_id INTEGER NOT NULL REFERENCES telegram_connection(id), generation TEXT NOT NULL,
      context_json TEXT NOT NULL, bot_identity INTEGER NOT NULL, bot_fingerprint TEXT NOT NULL,
      created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS telegram_meeting_origin_owner ON telegram_meeting_origin(account_id,expires_at);
    DROP TRIGGER IF EXISTS telegram_task_proposal_delete;
    CREATE TRIGGER telegram_task_proposal_delete BEFORE DELETE ON work_task
    BEGIN
      UPDATE telegram_preview SET state='cancelled',fields_json=NULL,summary_json=NULL,expected_json=NULL
        WHERE state='pending' AND operation_id IN
          (SELECT operation_id FROM telegram_operation WHERE action IN ('tasks.deadline','tasks.accept','tasks.return','tasks.assign','tasks.reassign','tasks.reopen','tasks.cancel') AND target_id=OLD.id);
      UPDATE telegram_operation SET target_id=NULL,result_code='task_deleted'
        WHERE action IN ('tasks.create','tasks.deadline','tasks.accept','tasks.return','tasks.assign','tasks.reassign','tasks.reopen','tasks.cancel') AND target_id=OLD.id;
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_calendar_receipt_delete BEFORE DELETE ON calendar_entry
    BEGIN
      UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,error_code='calendar_deleted'
        WHERE operation_id IN (SELECT operation_id FROM telegram_operation WHERE result_entry_id=OLD.id)
          AND state IN ('queued','claimed','sending','retry_wait');
      UPDATE telegram_operation SET result_entry_id=NULL,result_code='calendar_deleted'
        WHERE result_entry_id=OLD.id;
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_room_receipt_delete BEFORE DELETE ON room_reservation
    BEGIN
      UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,error_code='room_deleted'
        WHERE operation_id IN (SELECT operation_id FROM telegram_operation WHERE result_room_id=OLD.id)
          AND state IN ('queued','claimed','sending','retry_wait');
      UPDATE telegram_operation SET result_room_id=NULL,result_code='room_deleted' WHERE result_room_id=OLD.id;
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_room_calendar_grant AFTER UPDATE OF revoked_at ON telegram_grant
    WHEN NEW.action='calendar.read' AND NEW.revoked_at IS NOT NULL
    BEGIN
      UPDATE telegram_preview SET state='cancelled',fields_json=NULL,summary_json=NULL,expected_json=NULL
        WHERE connection_id=NEW.connection_id AND generation=NEW.generation AND action='rooms.request' AND state='pending';
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_combined_room_grant AFTER UPDATE OF revoked_at ON telegram_grant
    WHEN NEW.action IN ('rooms.read','rooms.request') AND NEW.revoked_at IS NOT NULL
    BEGIN
      UPDATE telegram_preview SET state='cancelled',fields_json=NULL,summary_json=NULL,expected_json=NULL
        WHERE connection_id=NEW.connection_id AND generation=NEW.generation AND action='calendar.create'
          AND state='pending' AND json_type(fields_json,'$.room')='object';
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_preview_cancel AFTER UPDATE OF state ON telegram_preview
    WHEN NEW.state='cancelled'
    BEGIN
      UPDATE telegram_operation SET state='cancelled',result_code='preview_cancelled',
        updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE operation_id=NEW.operation_id AND state='pending';
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_preview_connection AFTER UPDATE OF state,generation ON telegram_connection
    WHEN OLD.state IS NOT NEW.state OR OLD.generation IS NOT NEW.generation
    BEGIN
      UPDATE telegram_preview SET state='cancelled',fields_json=NULL,summary_json=NULL,expected_json=NULL
        WHERE connection_id=NEW.id AND state='pending';
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_preview_group AFTER UPDATE OF state,generation ON telegram_group
    WHEN OLD.state IS NOT NEW.state OR OLD.generation IS NOT NEW.generation
    BEGIN
      UPDATE telegram_preview SET state='cancelled',fields_json=NULL,summary_json=NULL,expected_json=NULL
        WHERE registration_id=NEW.id AND state='pending';
    END;
    DROP TRIGGER IF EXISTS telegram_preview_grant;
    CREATE TRIGGER telegram_preview_grant AFTER UPDATE OF revoked_at ON telegram_grant
    WHEN NEW.revoked_at IS NOT NULL
    BEGIN
      UPDATE telegram_preview SET state='cancelled',fields_json=NULL,summary_json=NULL,expected_json=NULL
        WHERE connection_id=NEW.connection_id AND generation=NEW.generation AND state='pending'
        AND (action=NEW.action OR (NEW.action='calendar.read' AND action IN ('calendar.create','calendar.reschedule','calendar.cancel'))
          OR (NEW.action='rooms.read' AND action IN ('rooms.request','rooms.withdraw','rooms.move'))
          OR (NEW.action='calendar.read' AND action='rooms.move'
              AND json_extract(CASE WHEN json_valid(expected_json) THEN expected_json ELSE '{}' END,'$.entry_id') IS NOT NULL)
          OR (NEW.action='work.read' AND action IN ('tasks.acknowledge','tasks.submit','tasks.create','tasks.deadline','tasks.accept','tasks.return','tasks.assign','tasks.reassign','tasks.reopen','tasks.cancel')));
    END;
    CREATE TRIGGER IF NOT EXISTS telegram_account_revoked
    AFTER UPDATE OF active,must_change,role,username,pw_hash,salt ON admin_user
    WHEN OLD.active IS NOT NEW.active OR OLD.must_change IS NOT NEW.must_change
      OR OLD.role IS NOT NEW.role OR OLD.username IS NOT NEW.username
      OR OLD.pw_hash IS NOT NEW.pw_hash OR OLD.salt IS NOT NEW.salt
    BEGIN
      UPDATE telegram_update SET state='cancelled',payload_json=NULL,claim_token=NULL,lease_until=NULL,
        error_code='account_changed' WHERE state IN ('queued','processing') AND
        (connection_id IN (SELECT id FROM telegram_connection WHERE account_id=NEW.id)
        OR sender_id IN (SELECT telegram_user_id FROM telegram_link_challenge WHERE account_id=NEW.id AND state IN ('issued','claimed')));
      UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,projection_json='{}',error_code='account_changed',
        updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE state IN ('queued','claimed','retry_wait','sending') AND
        (connection_id IN (SELECT id FROM telegram_connection WHERE account_id=NEW.id)
        OR chat_id IN (SELECT telegram_user_id FROM telegram_link_challenge WHERE account_id=NEW.id AND state IN ('issued','claimed')));
      UPDATE telegram_grant SET revoked_at=COALESCE(revoked_at,strftime('%Y-%m-%dT%H:%M:%SZ','now')) WHERE account_id=NEW.id;
      UPDATE telegram_connection SET state='revoked',generation=lower(hex(randomblob(16))),
        revoked_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE account_id=NEW.id AND revoked_at IS NULL;
      UPDATE telegram_link_challenge SET state='cancelled',session_id=NULL
        WHERE account_id=NEW.id AND state IN ('issued','claimed');
      UPDATE telegram_operation SET state='cancelled',result_code='account_changed',updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE actor_id=NEW.id AND state='pending';
    END;
    ''')
    if 'action' not in {r[1] for r in conn.execute('PRAGMA table_info(telegram_meeting_origin)')}:
        conn.execute("ALTER TABLE telegram_meeting_origin ADD COLUMN action TEXT NOT NULL DEFAULT 'calendar.create'")
    if 'token_nonce' not in {r[1] for r in conn.execute('PRAGMA table_info(telegram_preview)')}:
        conn.execute('ALTER TABLE telegram_preview ADD COLUMN token_nonce TEXT')
    if 'context_json' not in {r[1] for r in conn.execute('PRAGMA table_info(telegram_operation)')}:
        conn.execute('ALTER TABLE telegram_operation ADD COLUMN context_json TEXT')
    if 'context_hash' not in {r[1] for r in conn.execute('PRAGMA table_info(telegram_operation)')}:
        conn.execute('ALTER TABLE telegram_operation ADD COLUMN context_hash TEXT')
    if 'parent_operation_id' not in {r[1] for r in conn.execute('PRAGMA table_info(telegram_operation)')}:
        conn.execute('ALTER TABLE telegram_operation ADD COLUMN parent_operation_id TEXT REFERENCES telegram_operation(operation_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS telegram_operation_parent ON telegram_operation(parent_operation_id)')
    columns={r[1] for r in conn.execute('PRAGMA table_info(telegram_connection)')}
    for name,kind in (('bot_identity','INTEGER'),('bot_fingerprint','TEXT')):
        if name not in columns:
            conn.execute('ALTER TABLE telegram_connection ADD COLUMN '+name+' '+kind)

    import telegram_changes
    telegram_changes.install(conn)
    import telegram_notices
    telegram_notices.install(conn)
    import telegram_preferences
    telegram_preferences.install(conn)
    import telegram_reminders
    telegram_reminders.install(conn)
    import telegram_brief_preferences
    telegram_brief_preferences.install(conn)


def reset_after_restore(conn):
    """Fence *every* snapshot recovery, including routine boot hydration.

    Caller owns the transaction. No schema installation here: a historical
    snapshot can predate any of these tables. Fresh random generations avoid
    collisions when an old snapshot rolls back a numeric revision counter.
    Later preview tables must extend this hook when introduced.
    """
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'telegram_change_event' in tables:
        import telegram_changes
        telegram_changes.reset_after_restore(conn)
    if 'telegram_meeting_origin' in tables:
        conn.execute('DELETE FROM telegram_meeting_origin')
    if 'telegram_preview' in tables:
        conn.execute("UPDATE telegram_preview SET state='cancelled',fields_json=NULL,summary_json=NULL,expected_json=NULL WHERE state='pending'")
    if 'telegram_group_share' in tables:
        conn.execute("UPDATE telegram_group_share SET revoked_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE revoked_at IS NULL")
    if 'telegram_group' in tables:
        conn.execute("UPDATE telegram_group SET state='paused',generation=lower(hex(randomblob(16))),reason='restored' WHERE state<>'revoked'")
    if 'telegram_group_request' in tables:
        conn.execute("UPDATE telegram_group_request SET state='cancelled' WHERE state='observed'")
    if 'telegram_link_challenge' in tables:
        conn.execute("UPDATE telegram_link_challenge SET state='cancelled',session_id=NULL WHERE state IN ('issued','claimed')")
    if 'telegram_grant' in tables:
        conn.execute("UPDATE telegram_grant SET revoked_at=COALESCE(revoked_at,strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    if 'telegram_connection' in tables:
        conn.execute("""UPDATE telegram_connection SET
          state=CASE WHEN state='revoked' THEN 'revoked' ELSE 'paused' END,
          generation=lower(hex(randomblob(16))), updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')""")
    if 'telegram_update' in tables:
        conn.execute("""UPDATE telegram_update SET
          state=CASE WHEN state IN ('queued','processing') THEN 'cancelled' ELSE state END,
          payload_json=NULL, claim_token=NULL, lease_until=NULL,
          error_code=CASE WHEN state IN ('queued','processing') THEN 'restored' ELSE error_code END""")
    if 'telegram_operation' in tables:
        conn.execute("""UPDATE telegram_operation SET state='cancelled', result_code='restored',
          updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE state='pending'""")
    if 'telegram_delivery' in tables:
        conn.execute("""UPDATE telegram_delivery SET
          state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
          projection_json='{}', claim_token=NULL, lease_until=NULL, retry_at=NULL,
          error_code='restored', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
          WHERE state IN ('queued','claimed','sending','retry_wait')""")
