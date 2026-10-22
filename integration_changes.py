"""A21 durable change notices and opaque, identity-bound resume checkpoints."""
import secrets
import time

import documents_permissions as permissions
from documents_storage import rows, transaction

TTL = 7 * 86400


class CheckpointError(ValueError):
    pass


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS integration_stream (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), epoch TEXT NOT NULL);
    INSERT OR IGNORE INTO integration_stream VALUES(1,lower(hex(randomblob(16))));
    CREATE TABLE IF NOT EXISTS integration_change (
      sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
      entity TEXT NOT NULL CHECK(entity IN ('document','work_item','task')),
      entity_id INTEGER NOT NULL, case_id INTEGER,
      revision INTEGER NOT NULL CHECK(revision>0),
      recorded_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS integration_change_entity ON integration_change(entity,sequence);
    CREATE TRIGGER IF NOT EXISTS integration_change_no_update BEFORE UPDATE ON integration_change
      BEGIN SELECT RAISE(ABORT,'Integration change notices are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS integration_change_no_delete BEFORE DELETE ON integration_change
      BEGIN SELECT RAISE(ABORT,'Integration change notices are retained'); END;
    CREATE TABLE IF NOT EXISTS integration_checkpoint (
      id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, credential_id TEXT NOT NULL,
      resource TEXT NOT NULL, audience TEXT NOT NULL, epoch TEXT NOT NULL,
      position INTEGER NOT NULL, expires_at INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS integration_checkpoint_binding
      ON integration_checkpoint(owner_id,credential_id,resource,epoch,position);
    CREATE INDEX IF NOT EXISTS integration_checkpoint_expiry ON integration_checkpoint(expires_at);
    ''')
    # Capture the notice in the same writer transaction as the entity revision.
    # Existing records are deliberately not backfilled as fictitious changes.
    for table,entity,parent in (('document','document','NULL'),('work_case','work_item','NEW.id'),('work_task','task','NEW.case_id')):
        for action in ('INSERT','UPDATE'):
            condition = 'WHEN NEW.revision IS NOT OLD.revision' if action=='UPDATE' else ''
            conn.executescript(f'''
            CREATE TRIGGER IF NOT EXISTS integration_change_{table}_{action.lower()}
            AFTER {action} ON {table} {condition}
            BEGIN
              INSERT INTO integration_change(id,entity,entity_id,case_id,revision,recorded_at)
              VALUES(lower(hex(randomblob(16))),'{entity}',NEW.id,{parent},NEW.revision,
                     strftime('%Y-%m-%dT%H:%M:%f+00:00','now'));
            END;
            ''')


def read(conn,user,credential_id,resource,audience,cursor,limit):
    epoch = conn.execute('SELECT epoch FROM integration_stream WHERE singleton=1').fetchone()[0]
    high = conn.execute('SELECT COALESCE(MAX(sequence),0) FROM integration_change').fetchone()[0]
    binding = (user['id'],credential_id,resource,audience,epoch)
    if not cursor:
        return [],False,high,binding
    checkpoint = conn.execute('''SELECT position FROM integration_checkpoint
        WHERE id=? AND owner_id=? AND credential_id=? AND resource=? AND audience=? AND epoch=? AND expires_at>?''',
        (cursor,*binding,int(time.time()))).fetchone()
    if not checkpoint or checkpoint[0]>high:
        raise CheckpointError('Checkpoint unavailable. Start a new baseline and reconcile current records.')
    scope = permissions.RegistryScope(conn,user)
    if resource=='documents':
        selection = f'''SELECT e.* FROM integration_change e JOIN document d ON d.id=e.entity_id
            WHERE e.entity='document' AND d.canonical_id IS NULL AND {scope.view_sql('d')}'''
    else:
        selection = f'''SELECT e.* FROM integration_change e
            JOIN work_case wc ON wc.id=e.case_id
            LEFT JOIN work_task wt ON e.entity='task' AND wt.id=e.entity_id AND wt.case_id=wc.id
            WHERE e.entity IN ('work_item','task') AND ((e.entity='work_item' AND e.entity_id=wc.id) OR wt.id IS NOT NULL)
              AND {scope.work_view_sql('wc')}'''
    selected = rows(conn,selection+''' AND e.sequence>:after AND e.sequence<=:high
        ORDER BY e.sequence LIMIT :take''',
        {**scope.params,'after':checkpoint[0],'high':high,'take':limit+1})
    more = len(selected)>limit
    selected = selected[:limit]
    # An empty poll does not reveal hidden activity through a changed cursor.
    position = selected[-1]['sequence'] if selected else checkpoint[0]
    return selected,more,position,binding


def save(conn,binding,position,*,fresh=False):
    now = int(time.time())
    with transaction(conn):
        if conn.execute('SELECT epoch FROM integration_stream WHERE singleton=1').fetchone()[0] != binding[-1]:
            raise CheckpointError('Checkpoint unavailable. Start a new baseline and reconcile current records.')
        conn.execute('''DELETE FROM integration_checkpoint WHERE id IN
            (SELECT id FROM integration_checkpoint WHERE expires_at<=? LIMIT 200)''',(now,))
        previous = None if fresh else conn.execute('''SELECT id FROM integration_checkpoint
            WHERE owner_id=? AND credential_id=? AND resource=? AND audience=? AND epoch=? AND position=? AND expires_at>?
            ORDER BY expires_at DESC LIMIT 1''',(*binding,position,now)).fetchone()
        key = previous[0] if previous else secrets.token_hex(32)
        if previous:
            conn.execute('UPDATE integration_checkpoint SET expires_at=? WHERE id=?',(now+TTL,key))
        else:
            conn.execute('INSERT INTO integration_checkpoint VALUES(?,?,?,?,?,?,?,?)',(key,*binding,position,now+TTL))
    return key


def reset_after_restore(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='integration_stream'").fetchone():
        conn.execute('UPDATE integration_stream SET epoch=? WHERE singleton=1',(secrets.token_hex(16),))
        conn.execute('DELETE FROM integration_checkpoint')
