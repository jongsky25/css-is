"""Durable two-way Telegram storage. Business actions remain separately gated."""
import os


# Deliberately independent of Apprise's private discussion digest switch.
SWITCHES = (
    'inbound', 'delivery', 'link', 'groups', 'calendar_read', 'rooms_read',
    'calendar_create', 'rooms_request', 'change_notices', 'reminders',
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
      input_hash TEXT NOT NULL, target_id INTEGER, expected_revision TEXT,
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


def reset_after_restore(conn):
    """Fence *every* snapshot recovery, including routine boot hydration.

    Caller owns the transaction. No schema installation here: a historical
    snapshot can predate any of these tables. Fresh random generations avoid
    collisions when an old snapshot rolls back a numeric revision counter.
    Later preview/group tables must extend this hook when introduced.
    """
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
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
