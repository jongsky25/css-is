"""Inert two-way Telegram storage. No receiver, sender or business actions."""
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
    ''')


def reset_after_restore(conn):
    """Fence *every* snapshot recovery, including routine boot hydration.

    Caller owns the transaction. No schema installation here: a historical
    snapshot can predate any of these tables. Fresh random generations avoid
    collisions when an old snapshot rolls back a numeric revision counter.
    Later link/grant/preview/group tables must extend this hook when introduced.
    """
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
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
