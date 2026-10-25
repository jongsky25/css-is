"""Transactional change metadata and dormant, permission-checked route staging.

No business action, message rendering, provider send or external credential is
implemented here. T4.2 must reuse current route authorization at final delivery.
"""
from datetime import timedelta
import json
import time

from documents_storage import rows,transaction

EPOCH_KEY='telegram_change_epoch'
BATCH=20
TTL=timedelta(hours=24)

# Business columns are discovered from these owned tables. Read acknowledgements,
# courtesy timestamps and email/bell outboxes deliberately do not create events.
ROOTS={'calendar_entry':('calendar',{'updated_at','updated_by','created_at','css_nudged_at'}),
       'room_reservation':('room',{'updated_at','created_at','ext_email_verified_at','ext_consent_at'})}
CHILDREN={'calendar_entry_person':('calendar','entry_id',{'seen_seq','added_at','added_by'}),
          'calendar_entry_tag':('calendar','entry_id',set()),
          'calendar_entry_unit':('calendar','entry_id',set()),
          'calendar_entry_doc':('calendar','entry_id',{'updated_at','updated_by'}),
          'calendar_entry_outside':('calendar','entry_id',{'updated_at','updated_by'}),
          'calendar_entry_dpo_cites':('calendar','entry_id',{'updated_at','updated_by'}),
          'room_reservation_slot':('room','reservation_id',set())}


def _capture(entity,source,kind,*,condition='1',fresh=False,deleted=False):
    # Identifiers/expressions come only from the static install inventory below.
    return f"""
      INSERT INTO telegram_change_head(entity,source_id,incarnation,revision,deleted)
        SELECT '{entity}',{source},lower(hex(randomblob(16))),1,{int(deleted)} WHERE {condition}
        ON CONFLICT(entity,source_id) DO UPDATE SET
          incarnation={'excluded.incarnation' if fresh else 'telegram_change_head.incarnation'},
          revision={'1' if fresh else 'telegram_change_head.revision+1'},deleted=excluded.deleted;
      UPDATE telegram_change_route SET state='cancelled',reason='source_changed'
        WHERE state='prepared' AND ({condition}) AND event_key IN
          (SELECT event_key FROM telegram_change_event WHERE entity='{entity}' AND source_id={source} AND state IN ('pending','routed'));
      UPDATE telegram_change_event SET state='superseded'
        WHERE entity='{entity}' AND source_id={source} AND state IN ('pending','routed') AND ({condition});
      INSERT INTO telegram_change_event(event_key,epoch,entity,source_id,incarnation,revision,kind,recorded_at)
        SELECT lower(hex(randomblob(16))),(SELECT value FROM app_setting WHERE key='{EPOCH_KEY}'),
          entity,source_id,incarnation,revision,'{kind}',strftime('%Y-%m-%dT%H:%M:%SZ','now')
        FROM telegram_change_head WHERE entity='{entity}' AND source_id={source} AND ({condition});
    """


def _changed(conn,table,ignored):
    columns=[r[1] for r in conn.execute('PRAGMA table_info('+table+')') if r[1] not in ignored|{'id'}]
    return ' OR '.join('NEW.'+c+' IS NOT OLD.'+c for c in columns) or '0'


def install(conn):
    conn.executescript(f"""
    INSERT OR IGNORE INTO app_setting(key,value) VALUES('{EPOCH_KEY}',lower(hex(randomblob(16))));
    CREATE TABLE IF NOT EXISTS telegram_change_head(
      entity TEXT NOT NULL, source_id INTEGER NOT NULL, incarnation TEXT NOT NULL,
      revision INTEGER NOT NULL CHECK(revision>0),deleted INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(entity,source_id));
    CREATE TABLE IF NOT EXISTS telegram_change_event(
      sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_key TEXT NOT NULL UNIQUE,epoch TEXT NOT NULL,
      entity TEXT NOT NULL,source_id INTEGER NOT NULL,incarnation TEXT NOT NULL,revision INTEGER NOT NULL,
      kind TEXT NOT NULL,recorded_at TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','routed','superseded','cancelled')),
      private_after INTEGER NOT NULL DEFAULT 0,private_done INTEGER NOT NULL DEFAULT 0,
      group_after INTEGER NOT NULL DEFAULT 0,
      UNIQUE(epoch,entity,source_id,incarnation,revision));
    CREATE INDEX IF NOT EXISTS telegram_change_queue ON telegram_change_event(state,sequence);
    CREATE INDEX IF NOT EXISTS telegram_change_source ON telegram_change_event(entity,source_id,state);
    CREATE TABLE IF NOT EXISTS telegram_change_route(
      id INTEGER PRIMARY KEY,event_key TEXT NOT NULL REFERENCES telegram_change_event(event_key),
      connection_id INTEGER NOT NULL REFERENCES telegram_connection(id),generation TEXT NOT NULL,
      chat_id INTEGER NOT NULL,topic_id INTEGER NOT NULL DEFAULT 0,
      registration_id INTEGER,registration_generation TEXT,
      bot_identity INTEGER NOT NULL,bot_fingerprint TEXT NOT NULL,
      projection TEXT NOT NULL CHECK(projection IN ('calendar_private','calendar_shared','room_private','room_availability')),
      state TEXT NOT NULL DEFAULT 'prepared' CHECK(state IN ('prepared','cancelled')),
      reason TEXT,created_at TEXT NOT NULL,
      UNIQUE(event_key,chat_id,topic_id));
    CREATE INDEX IF NOT EXISTS telegram_change_route_state ON telegram_change_route(state,id);
    CREATE INDEX IF NOT EXISTS telegram_change_route_connection ON telegram_change_route(connection_id,state);
    CREATE INDEX IF NOT EXISTS telegram_change_route_group ON telegram_change_route(registration_id,state);
    CREATE INDEX IF NOT EXISTS telegram_operation_room_result ON telegram_operation(result_room_id,action);
    CREATE TRIGGER IF NOT EXISTS telegram_change_immutable BEFORE UPDATE OF
      event_key,epoch,entity,source_id,incarnation,revision,kind,recorded_at ON telegram_change_event
      BEGIN SELECT RAISE(ABORT,'Change metadata is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS telegram_change_connection AFTER UPDATE OF state,generation ON telegram_connection
      WHEN NEW.state IS NOT OLD.state OR NEW.generation IS NOT OLD.generation
      BEGIN UPDATE telegram_change_route SET state='cancelled',reason='connection_changed'
        WHERE connection_id=NEW.id AND state='prepared'; END;
    CREATE TRIGGER IF NOT EXISTS telegram_change_group AFTER UPDATE OF state,generation ON telegram_group
      WHEN NEW.state IS NOT OLD.state OR NEW.generation IS NOT OLD.generation
      BEGIN UPDATE telegram_change_route SET state='cancelled',reason='group_changed'
        WHERE registration_id=NEW.id AND state='prepared'; END;
    CREATE TRIGGER IF NOT EXISTS telegram_change_grant AFTER UPDATE OF revoked_at ON telegram_grant
      WHEN NEW.revoked_at IS NOT NULL
      BEGIN UPDATE telegram_change_route SET state='cancelled',reason='grant_changed'
        WHERE connection_id=NEW.connection_id AND generation=NEW.generation AND state='prepared'
          AND ((NEW.action='calendar.read' AND projection LIKE 'calendar_%')
            OR (NEW.action='rooms.read' AND projection IN ('room_private','room_availability'))); END;
    """)
    for action in ('UPDATE','DELETE'):
        ref='NEW' if action=='UPDATE' else 'OLD'
        conn.executescript(f"""CREATE TRIGGER IF NOT EXISTS telegram_change_share_{action.lower()}
          AFTER {action} ON telegram_group_share BEGIN
          UPDATE telegram_change_route SET state='cancelled',reason='share_changed'
          WHERE state='prepared' AND projection='calendar_shared' AND registration_id={ref}.registration_id
            AND event_key IN (SELECT event_key FROM telegram_change_event
              WHERE entity='calendar' AND source_id={ref}.entry_id); END;""")
    for table,(entity,ignored) in ROOTS.items():
        for action in ('INSERT','UPDATE','DELETE'):
            ref='OLD' if action=='DELETE' else 'NEW'
            when='WHEN '+_changed(conn,table,ignored) if action=='UPDATE' else ''
            body=_capture(entity,ref+'.id',entity+'.'+action.lower(),fresh=action=='INSERT',deleted=action=='DELETE')
            conn.executescript(f'CREATE TRIGGER IF NOT EXISTS telegram_change_{table}_{action.lower()} AFTER {action} ON {table} {when} BEGIN {body} END;')
    for table,(entity,column,ignored) in CHILDREN.items():
        parent='calendar_entry' if entity=='calendar' else 'room_reservation'
        for action in ('INSERT','UPDATE','DELETE'):
            ref='OLD' if action=='DELETE' else 'NEW';source=ref+'.'+column
            when='WHEN '+_changed(conn,table,ignored) if action=='UPDATE' else ''
            body=_capture(entity,source,entity+'.details',condition=f'EXISTS(SELECT 1 FROM {parent} WHERE id={source})')
            if action=='UPDATE':
                body=_capture(entity,'OLD.'+column,entity+'.details',condition=f'OLD.{column} IS NOT NEW.{column} AND EXISTS(SELECT 1 FROM {parent} WHERE id=OLD.{column})')+body
            conn.executescript(f'CREATE TRIGGER IF NOT EXISTS telegram_change_{table}_{action.lower()} AFTER {action} ON {table} {when} BEGIN {body} END;')
    # Config/availability changes are retained without inventing a subscription.
    # T4.2 may define a separately reviewed anonymous availability notification.
    for table,ignored in (('room_slot',set()),('room_block',{'created_at','created_by'})):
        for action in ('INSERT','UPDATE','DELETE'):
            when='WHEN '+_changed(conn,table,ignored) if action=='UPDATE' else ''
            body=_capture('availability','1','availability.changed')
            conn.executescript(f'CREATE TRIGGER IF NOT EXISTS telegram_change_{table}_{action.lower()} AFTER {action} ON {table} {when} BEGIN {body} END;')
    # CSS activity dates/details can change outside the overlay writer.
    for action in ('UPDATE','DELETE'):
        when=('WHEN '+' OR '.join('NEW.'+c+' IS NOT OLD.'+c for c in ('title','event_date','end_date','venue','modality','organizer','lead_org_id'))) if action=='UPDATE' else ''
        # An activity has at most one stored calendar overlay.
        source='(SELECT id FROM calendar_entry WHERE event_id=OLD.id)'
        body=_capture('calendar',source,'calendar.activity',condition=f'{source} IS NOT NULL')
        conn.executescript(f'CREATE TRIGGER IF NOT EXISTS telegram_change_activity_{action.lower()} AFTER {action} ON event {when} BEGIN {body} END;')


def enabled():
    import telegram_links as links
    import telegram_storage as switches
    return (all(switches.enabled(k) for k in ('inbound','delivery','link','change_notices')) and links.available())


def current(conn,event,now):
    import telegram_links as links
    epoch=conn.execute('SELECT value FROM app_setting WHERE key=?',(EPOCH_KEY,)).fetchone()
    head=conn.execute('SELECT incarnation,revision,deleted FROM telegram_change_head WHERE entity=? AND source_id=?',
                      (event['entity'],event['source_id'])).fetchone()
    return bool(epoch and event['epoch']==epoch[0] and head and tuple(head)==(event['incarnation'],event['revision'],0)
                and event['recorded_at']>links.stamp(now-TTL))


def _private(conn,event,connection,bot):
    import office_calendar as calendar
    import rooms
    import telegram_calendar as common
    d={'connection_id':connection['id'],'generation':connection['generation'],'chat_id':connection['private_chat_id'],
       'topic_id':None,'registration_id':None}
    action='calendar.read' if event['entity']=='calendar' else 'rooms.read'
    user=common.actor(conn,d,bot,action)
    if not user or connection['bot_identity']!=bot[0] or connection['bot_fingerprint']!=bot[2]:return None
    if event['entity']=='calendar':
        entry=calendar.viewable_entry(conn,user,event['source_id'])
        if not entry or not (entry['created_by']==user['username'] or any(p['user_id']==user['id'] for p in entry['people'])):return None
        return 'calendar_private'
    if event['entity']=='room':
        record=rooms.get_reservation(conn,event['source_id'])
        if record and record['requester_user_id']==user['id']:return 'room_private'
    return None


def _group(conn,event,group,bot):
    import rooms
    import telegram_group_reads as shared
    import telegram_groups as groups
    import telegram_links as links
    connection=groups.linked(conn,group['owner_account_id'],admin=True)
    projection='calendar_shared'
    if event['entity']=='calendar':
        if not links.authorized(conn,group['owner_account_id'],'calendar.read'):return None
        user=rows(conn,'SELECT id,username,role FROM admin_user WHERE id=?',(group['owner_account_id'],))[0]
        entry=shared.shareable(conn,user,event['source_id'])
        if not entry or not conn.execute('''SELECT 1 FROM telegram_group_share WHERE entry_id=? AND registration_id=?
            AND registration_generation=? AND revoked_at IS NULL AND revision=?''',
            (entry['id'],group['id'],group['generation'],shared.revision(entry))).fetchone():return None
    elif event['entity']=='room':
        # Anonymous availability goes only to the room action's original exact group.
        ops=rows(conn,"SELECT context_json FROM telegram_operation WHERE action='rooms.request' AND result_room_id=? LIMIT 1",(event['source_id'],))
        try:ctx=json.loads(ops[0]['context_json'])
        except (IndexError,TypeError,ValueError):return None
        if (ctx.get('registration_id')!=group['id'] or ctx.get('registration_generation')!=group['generation']
                or ctx.get('chat_id')!=group['chat_id'] or (ctx.get('topic_id') or 0)!=group['topic_id']):return None
        found=rows(conn,'SELECT * FROM telegram_connection WHERE id=? AND generation=? AND state=\'active\'',(ctx.get('connection_id'),ctx.get('generation')))
        if (not found or found[0]['telegram_user_id']!=ctx.get('sender_id') or found[0]['private_chat_id']!=ctx.get('sender_id')
                or not links.authorized(conn,found[0]['account_id'],'rooms.read')):return None
        record=rooms.get_reservation(conn,event['source_id'])
        if not record or record['requester_user_id']!=found[0]['account_id']:return None
        connection=found[0];projection='room_availability'
    else:return None
    if not groups.route(conn,group['chat_id'],group['topic_id'],bot):return None
    if connection['bot_identity']!=bot[0] or connection['bot_fingerprint']!=bot[2]:return None
    return connection,projection


def _insert(conn,event,connection,bot,projection,now,group=None):
    import telegram_links as links
    conn.execute('''INSERT INTO telegram_change_route(event_key,connection_id,generation,chat_id,topic_id,
        registration_id,registration_generation,bot_identity,bot_fingerprint,projection,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_key,chat_id,topic_id) DO NOTHING''',
        (event['event_key'],connection['id'],connection['generation'],group['chat_id'] if group else connection['private_chat_id'],
         group['topic_id'] if group else 0,group['id'] if group else None,group['generation'] if group else None,
         bot[0],bot[2],projection,links.stamp(now)))


def prepare_routes(conn,now):
    """One event, at most 20 connections and 20 groups per call; no provider I/O."""
    import telegram_transport as transport
    if not enabled():return 0
    with transaction(conn):
        bot=transport.config()
        if not bot or not enabled():return 0
        found=rows(conn,"SELECT * FROM telegram_change_event WHERE state='pending' ORDER BY sequence LIMIT 1")
        if not found:return 0
        event=found[0]
        if not current(conn,event,now) or event['entity'] not in ('calendar','room'):
            conn.execute("UPDATE telegram_change_event SET state='cancelled' WHERE event_key=?",(event['event_key'],));return 0
        count=0
        if not event['private_done']:
            candidates=rows(conn,"SELECT * FROM telegram_connection WHERE id>? AND state='active' ORDER BY id LIMIT ?",(event['private_after'],BATCH+1))
            for connection in candidates[:BATCH]:
                projection=_private(conn,event,connection,bot)
                if projection:_insert(conn,event,connection,bot,projection,now);count+=1
            done=len(candidates)<=BATCH
            conn.execute('UPDATE telegram_change_event SET private_after=?,private_done=? WHERE event_key=?',
                         (candidates[min(len(candidates),BATCH)-1]['id'] if candidates else event['private_after'],int(done),event['event_key']))
            if not done:return count
        candidates=rows(conn,"SELECT * FROM telegram_group WHERE id>? AND state='active' ORDER BY id LIMIT ?",(event['group_after'],BATCH+1))
        for group in candidates[:BATCH]:
            try:allowed=_group(conn,event,group,bot)
            except ValueError:allowed=None
            if allowed:_insert(conn,event,allowed[0],bot,allowed[1],now,group);count+=1
        conn.execute('UPDATE telegram_change_event SET group_after=?,state=? WHERE event_key=?',
                     (candidates[min(len(candidates),BATCH)-1]['id'] if candidates else event['group_after'],
                      'routed' if len(candidates)<=BATCH else 'pending',event['event_key']))
        return count


def authorize_route(conn,identifier,now):
    """Current local eligibility, never an authorization to render arbitrary data."""
    import telegram_groups as groups
    import telegram_transport as transport
    if not enabled():return None
    found=rows(conn,"SELECT * FROM telegram_change_route WHERE id=? AND state='prepared'",(identifier,))
    if not found:return None
    route=found[0];bot=transport.config()
    if not bot or (route['bot_identity'],route['bot_fingerprint'])!=(bot[0],bot[2]):return None
    event=rows(conn,'SELECT * FROM telegram_change_event WHERE event_key=?',(route['event_key'],))[0]
    if not current(conn,event,now) or event['state'] not in ('pending','routed'):return None
    found=rows(conn,'SELECT * FROM telegram_connection WHERE id=? AND generation=? AND state=\'active\'',(route['connection_id'],route['generation']))
    if not found:return None
    connection=found[0]
    if route['chat_id']>0:
        if route['registration_id'] is not None or route['topic_id']!=0 or route['chat_id']!=connection['private_chat_id']:return None
        if _private(conn,event,connection,bot)!=route['projection']:return None
    else:
        group=groups.route(conn,route['chat_id'],route['topic_id'],bot)
        if not group or group['id']!=route['registration_id'] or group['generation']!=route['registration_generation']:return None
        try:allowed=_group(conn,event,group,bot)
        except ValueError:return None
        if not allowed or allowed[0]['id']!=route['connection_id'] or allowed[0]['generation']!=route['generation'] or allowed[1]!=route['projection']:return None
    return route,event


def verify_route(conn,identifier,now):
    """Fresh group proof outside the writer, then local recheck. Does not send."""
    import rooms
    import storage as st
    import telegram_groups as groups
    import telegram_transport as transport
    started=time.monotonic()
    with transaction(conn):allowed=authorize_route(conn,identifier,now)
    if not allowed:return False
    route,event=allowed
    if route['chat_id']<0:
        source=st.cal_get(conn,event['source_id']) if event['entity']=='calendar' else rooms.get_reservation(conn,event['source_id'])
        if not source:return False
        query={'mode':'calendar','start':source['start_date'],'end':source['start_date']} if event['entity']=='calendar' else {'mode':'rooms','day':source['day']}
        d={**route,'projection_json':json.dumps({'kind':'group_read','bot':route['bot_identity'],'fingerprint':route['bot_fingerprint'],'query':query})}
        if not groups.verify_delivery(conn,d,transport.config()):return False
    with transaction(conn):return authorize_route(conn,identifier,now+timedelta(seconds=time.monotonic()-started)) is not None


def cleanup_in_transaction(conn,now):
    import telegram_links as links
    conn.execute("UPDATE telegram_change_event SET state='cancelled' WHERE event_key IN (SELECT event_key FROM telegram_change_event WHERE state='pending' AND recorded_at<=? LIMIT 20)",(links.stamp(now-TTL),))
    # Recheck a bounded set after env/directory changes that have no SQL trigger.
    pending=rows(conn,"SELECT id FROM telegram_change_route WHERE state='prepared' ORDER BY id LIMIT 20")
    for item in pending:
        if not authorize_route(conn,item['id'],now):
            conn.execute("UPDATE telegram_change_route SET state='cancelled',reason='ineligible' WHERE id=?",(item['id'],))
    cutoff=links.stamp(now-timedelta(days=180))
    conn.execute("DELETE FROM telegram_change_route WHERE id IN (SELECT id FROM telegram_change_route WHERE state='cancelled' AND created_at<? LIMIT 20)",(links.stamp(now-timedelta(days=30)),))
    conn.execute("DELETE FROM telegram_change_event WHERE event_key IN (SELECT e.event_key FROM telegram_change_event e WHERE state<>'pending' AND recorded_at<? AND NOT EXISTS(SELECT 1 FROM telegram_change_route r WHERE r.event_key=e.event_key) LIMIT 20)",(cutoff,))


def reset_after_restore(conn):
    conn.execute('UPDATE app_setting SET value=lower(hex(randomblob(16))) WHERE key=?',(EPOCH_KEY,))
    conn.execute("UPDATE telegram_change_event SET state='cancelled' WHERE state IN ('pending','routed')")
    conn.execute("UPDATE telegram_change_route SET state='cancelled',reason='restored' WHERE state='prepared'")
