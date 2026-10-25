"""Current change projections handed off atomically to the existing sender.

Queues contain identifiers only. Business records are never changed by a notice.
"""
from datetime import datetime,timedelta
import json
import re

from documents_storage import rows,transaction
import telegram_changes as changes
import telegram_preferences as preferences
import telegram_links as links
import telegram_transport as transport

KIND='change_notice'


def install(conn):
    if 'delivery_key' not in {r[1] for r in conn.execute('PRAGMA table_info(telegram_change_route)')}:
        conn.execute('ALTER TABLE telegram_change_route ADD COLUMN delivery_key TEXT')
    conn.executescript('''
    CREATE INDEX IF NOT EXISTS telegram_notice_handoff ON telegram_change_route(state,delivery_key,id);
    CREATE TABLE IF NOT EXISTS telegram_notice_pause(
      bot_fingerprint TEXT NOT NULL,chat_id INTEGER NOT NULL,topic_id INTEGER NOT NULL,
      connection_id INTEGER NOT NULL,generation TEXT NOT NULL,
      registration_id INTEGER,registration_generation TEXT,rejected_at TEXT NOT NULL,
      PRIMARY KEY(bot_fingerprint,chat_id,topic_id));
    CREATE INDEX IF NOT EXISTS telegram_notice_pause_age ON telegram_notice_pause(rejected_at);
    CREATE INDEX IF NOT EXISTS telegram_notice_pause_connection ON telegram_notice_pause(connection_id,generation,chat_id,topic_id);
    CREATE TRIGGER IF NOT EXISTS telegram_notice_route_fence AFTER UPDATE OF state ON telegram_change_route
      WHEN NEW.state='cancelled' AND OLD.state<>'cancelled'
      BEGIN
        UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
          claim_token=NULL,lease_until=NULL,error_code='notice_route_cancelled'
          WHERE dedupe_key=NEW.delivery_key AND state IN ('queued','claimed','retry_wait','sending');
      END;
    ''')
    for action in ('INSERT','UPDATE OF state'):
        name='insert' if action=='INSERT' else 'processed'
        conn.executescript(f'''CREATE TRIGGER IF NOT EXISTS telegram_notice_recover_{name}
          AFTER {action} ON telegram_update WHEN NEW.state='processed'
          BEGIN DELETE FROM telegram_notice_pause WHERE NEW.connection_id IS NOT NULL
            AND ((registration_id IS NULL AND connection_id=NEW.connection_id AND generation=NEW.generation) OR registration_id IS NOT NULL)
            AND chat_id=NEW.chat_id AND topic_id=COALESCE(NEW.topic_id,0) AND rejected_at<NEW.received_at; END;''')


def descriptor(p,bot):
    return (isinstance(p,dict) and set(p)=={'kind','route','event','bot','fingerprint'}
            and p['kind']==KIND and type(p['route']) is int and p['route']>0
            and isinstance(p['event'],str) and re.fullmatch('[a-f0-9]{32}',p['event']) is not None
            and p['bot']==bot[0] and p['fingerprint']==bot[2])


def paused(conn,route):
    found=rows(conn,'SELECT * FROM telegram_notice_pause WHERE bot_fingerprint=? AND chat_id=? AND topic_id=?',
               (route['bot_fingerprint'],route['chat_id'],route['topic_id']))
    if not found:return False
    pause=found[0]
    keys=('registration_id','registration_generation') if route['registration_id'] is not None else ('connection_id','generation','registration_id')
    if any(pause[k]!=route[k] for k in keys):return False
    # A new authenticated, recognized command in the same conversation is the
    # recovery signal. Duplicate/ignored/cancelled updates do not clear a pause.
    return not conn.execute('''SELECT 1 FROM telegram_update WHERE connection_id IS NOT NULL
        AND (? IS NOT NULL OR (connection_id=? AND generation=?))
        AND chat_id=? AND COALESCE(topic_id,0)=? AND state='processed' AND received_at>?
        LIMIT 1''',(route['registration_id'],route['connection_id'],route['generation'],route['chat_id'],route['topic_id'],pause['rejected_at'])).fetchone()



def enqueue(conn,now):
    if not changes.enabled():return 0
    with transaction(conn):
        bot=transport.config()
        if not bot or not changes.enabled():return 0
        candidates=rows(conn,"SELECT * FROM telegram_change_route WHERE state='prepared' AND delivery_key IS NULL ORDER BY id LIMIT 20")
        count=0
        for route in candidates:
            allowed=changes.authorize_route(conn,route['id'],now)
            if not allowed or paused(conn,route) or not preferences.telegram_enabled(conn,route):
                conn.execute("UPDATE telegram_change_route SET state='cancelled',reason=? WHERE id=?",('provider_paused' if allowed else 'ineligible',route['id']))
                continue
            route,event=allowed
            key='change:'+event['event_key']+':'+str(route['chat_id'])+':'+str(route['topic_id'])
            projection={'kind':KIND,'route':route['id'],'event':event['event_key'],'bot':bot[0],'fingerprint':bot[2]}
            expiry=links.stamp(datetime.fromisoformat(event['recorded_at'])+changes.TTL)
            due=preferences.delay_until(conn,route,now)
            if due and links.stamp(due)>=expiry:
                conn.execute("UPDATE telegram_change_route SET state='cancelled',reason='quiet_expiry' WHERE id=?",(route['id'],));continue
            conn.execute('''INSERT INTO telegram_delivery(dedupe_key,event_key,connection_id,generation,chat_id,topic_id,
                registration_id,registration_generation,projection_json,expires_at,created_at,updated_at,not_before)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO NOTHING''',
                (key,event['event_key'],route['connection_id'],route['generation'],route['chat_id'],route['topic_id'] or None,
                 route['registration_id'],route['registration_generation'],json.dumps(projection,sort_keys=True),expiry,links.stamp(now),links.stamp(now),links.stamp(due) if due else None))
            conn.execute('UPDATE telegram_change_route SET delivery_key=? WHERE id=? AND delivery_key IS NULL',(key,route['id']))
            count+=1
        return count


def allowed(conn,delivery,projection,bot,now,*,respect_quiet=True):
    if not descriptor(projection,bot):return None
    found=changes.authorize_route(conn,projection['route'],now)
    if not found:return None
    route,event=found
    if not preferences.telegram_enabled(conn,route) or (respect_quiet and preferences.delay_until(conn,route,now)):return None
    if (event['event_key']!=projection['event'] or delivery['event_key']!=event['event_key']
            or route['delivery_key']!=delivery['dedupe_key'] or paused(conn,route)
            or any(delivery[k]!=route[k] for k in ('connection_id','generation','chat_id','registration_id','registration_generation'))
            or (delivery['topic_id'] or 0)!=route['topic_id']):return None
    # Older queued attempts remain suppressed after a definite provider rejection.
    if conn.execute('''SELECT 1 FROM telegram_delivery WHERE chat_id=? AND COALESCE(topic_id,0)=?
        AND state='failed' AND error_code='provider_rejected' AND updated_at>=? LIMIT 1''',
        (delivery['chat_id'],route['topic_id'],delivery['created_at'])).fetchone():return None
    return route,event


def defer(conn,delivery,bot,now):
    try:p=json.loads(delivery['projection_json'])
    except (TypeError,ValueError):return False
    allowed_now=allowed(conn,delivery,p,bot,now,respect_quiet=False)
    if not allowed_now:return False
    route,event=allowed_now;due=preferences.delay_until(conn,route,now)
    if not due:return False
    if links.stamp(due)>=delivery['expires_at']:
        conn.execute("UPDATE telegram_change_route SET state='cancelled',reason='quiet_expiry' WHERE id=?",(route['id'],))
    else:
        conn.execute("UPDATE telegram_delivery SET not_before=?,state=CASE WHEN state='claimed' THEN 'queued' ELSE state END,claim_token=NULL,lease_until=NULL WHERE id=?",(links.stamp(due),delivery['id']))
    return True


def verify_delivery(conn,delivery,bot,now):
    try:projection=json.loads(delivery['projection_json'])
    except (ValueError,TypeError):return False
    if not allowed(conn,delivery,projection,bot,now):return False
    return changes.verify_route(conn,projection['route'],now)


def render(conn,delivery,projection,bot,now):
    import office_calendar as calendar
    import rooms
    import telegram_calendar as common
    import telegram_group_reads as shared
    with transaction(conn):
        found=allowed(conn,delivery,projection,bot,now)
        if not found:return None
        route,event=found;base=links.origin()
        if route['projection'] in ('calendar_private','calendar_shared'):
            connection=rows(conn,'''SELECT u.id,u.username,u.role FROM telegram_connection c JOIN admin_user u ON u.id=c.account_id WHERE c.id=?''',(route['connection_id'],))[0]
            entry=calendar.viewable_entry(conn,connection,event['source_id'])
            if not entry:return None
            heading='Calendar update' if route['projection']=='calendar_private' else 'Shared calendar update'
            return heading+' · current source\n'+shared.fields(entry)+'\n'+base+'/calendar/entries/'+str(entry['id'])
        record=rooms.get_reservation(conn,event['source_id'])
        if not record:return None
        if route['projection']=='room_private':
            status={'requested':'requested (pending Administrative Section approval; no booking held)',
                    'approved':'approved (booked)'}.get(record['status'],record['status'])
            return ('Room request update · current source\n'+common.clip(record['ref_code'],80)+' · '+record['day']+' · Asia/Manila\n'
                    +'Requested hours: '+common.clip(rooms.hours_text(conn,record),400)+'\nCurrent status: '+common.clip(status,150)
                    +'\n'+base+'/rooms/mine')
        view=rooms.day_view(conn,record['day'],today=now.astimezone(common.ZONE).date())
        text='Shared conference-room availability changed · Asia/Manila\n'+record['day']
        for slot in view['hours']:
            line=common.clip(slot['label'],80)+': '+slot['state']
            if common.units(text+'\n'+line)>2700:
                text+='\nMore slots on the signed-in page.';break
            text+='\n'+line
        return text+'\nBooked means approved; requested is pending approval with no hold. Current snapshot.\n'+base+'/rooms?day='+record['day']


def record_rejection(conn,delivery,now):
    """Called only after a matched notice failure finalizer, in its transaction."""
    try:p=json.loads(delivery['projection_json'])
    except (ValueError,TypeError):return
    bot=transport.config()
    if not bot or not descriptor(p,bot):return
    conn.execute('''INSERT INTO telegram_notice_pause(bot_fingerprint,chat_id,topic_id,connection_id,generation,
        registration_id,registration_generation,rejected_at) VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(bot_fingerprint,chat_id,topic_id) DO UPDATE SET connection_id=excluded.connection_id,
        generation=excluded.generation,registration_id=excluded.registration_id,
        registration_generation=excluded.registration_generation,rejected_at=excluded.rejected_at''',
        (bot[2],delivery['chat_id'],delivery['topic_id'] or 0,delivery['connection_id'],delivery['generation'],
         delivery['registration_id'],delivery['registration_generation'],links.stamp(now)))


def cleanup_in_transaction(conn,now):
    # Keep an active rejection pause until explicit recovery. Remove obsolete
    # bindings in bounded batches, without retaining unused numeric destinations.
    candidates=rows(conn,'SELECT * FROM telegram_notice_pause WHERE rejected_at<? LIMIT 20',(links.stamp(now-timedelta(days=30)),))
    bot=transport.config()
    for pause in candidates:
        current=True if pause['registration_id'] is not None else conn.execute("SELECT 1 FROM telegram_connection WHERE id=? AND generation=? AND state='active'",(pause['connection_id'],pause['generation'])).fetchone()
        group=True if pause['registration_id'] is None else conn.execute("SELECT 1 FROM telegram_group WHERE id=? AND generation=? AND state='active'",(pause['registration_id'],pause['registration_generation'])).fetchone()
        if not current or not group or (bot and bot[2]!=pause['bot_fingerprint']) or not paused(conn,pause):
            conn.execute('DELETE FROM telegram_notice_pause WHERE bot_fingerprint=? AND chat_id=? AND topic_id=?',
                         (pause['bot_fingerprint'],pause['chat_id'],pause['topic_id']))
