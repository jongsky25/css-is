"""Opt-in private reminders: durable occurrence tombstones, current data at I/O."""
from datetime import date,datetime,time,timedelta,timezone
import hashlib
import json
import re

from documents_storage import rows,transaction
import telegram_calendar as common
import telegram_links as links
import telegram_preferences as preferences
import telegram_storage as switches
import telegram_transport as transport

KIND='reminder'
LEADS=(0,15,30,60,1440)
USERS_PER_TICK=5
SOURCES_PER_USER=20


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS telegram_reminder_preference(
      user_id INTEGER PRIMARY KEY REFERENCES admin_user(id) ON DELETE CASCADE,
      calendar_minutes INTEGER NOT NULL DEFAULT 0 CHECK(calendar_minutes IN (0,15,30,60,1440)),
      room_minutes INTEGER NOT NULL DEFAULT 0 CHECK(room_minutes IN (0,15,30,60,1440)),
      revision INTEGER NOT NULL DEFAULT 0,calendar_after INTEGER NOT NULL DEFAULT 0,room_after INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS telegram_reminder_occurrence(
      occurrence_key TEXT PRIMARY KEY NOT NULL,created_at TEXT NOT NULL);
    INSERT OR IGNORE INTO app_setting(key,value) VALUES('telegram_reminder_after','0');
    ''')
    # Old sources predate change capture. Seed identity only, without inventing
    # a change event. Existing INSERT/DELETE capture protects numeric-ID reuse.
    for entity,table in (('calendar','calendar_entry'),('room','room_reservation')):
        conn.execute(f'''INSERT OR IGNORE INTO telegram_change_head(entity,source_id,incarnation,revision,deleted)
            SELECT ?,id,lower(hex(randomblob(16))),1,0 FROM {table}''',(entity,))
    conn.executescript('''
    CREATE TRIGGER IF NOT EXISTS telegram_reminder_source_fence AFTER UPDATE ON telegram_change_head
      WHEN NEW.revision IS NOT OLD.revision OR NEW.incarnation IS NOT OLD.incarnation OR NEW.deleted IS NOT OLD.deleted
      BEGIN UPDATE telegram_delivery SET state='uncertain',claim_token=NULL,lease_until=NULL,
        error_code='reminder_source_changed',updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE state='sending' AND dedupe_key LIKE 'reminder:%'
          AND json_extract(projection_json,'$.entity')=NEW.entity AND json_extract(projection_json,'$.source')=NEW.source_id; END;
    CREATE TRIGGER IF NOT EXISTS telegram_reminder_slot_fence AFTER UPDATE OF start_time,end_time ON room_slot
      WHEN NEW.start_time IS NOT OLD.start_time OR NEW.end_time IS NOT OLD.end_time
      BEGIN UPDATE telegram_delivery SET state='uncertain',claim_token=NULL,lease_until=NULL,error_code='reminder_slot_changed'
        WHERE state='sending' AND dedupe_key LIKE 'reminder:%' AND json_extract(projection_json,'$.entity')='room'
          AND json_extract(projection_json,'$.source') IN (SELECT reservation_id FROM room_reservation_slot WHERE slot_id=NEW.id); END;
    CREATE TRIGGER IF NOT EXISTS telegram_reminder_grant_fence AFTER UPDATE OF revoked_at ON telegram_grant
      WHEN NEW.revoked_at IS NOT NULL
      BEGIN UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,error_code='reminder_grant_revoked'
        WHERE connection_id=NEW.connection_id AND generation=NEW.generation AND dedupe_key LIKE 'reminder:%'
          AND state IN ('queued','claimed','retry_wait','sending')
          AND ((NEW.action='calendar.read' AND json_extract(projection_json,'$.entity')='calendar')
            OR (NEW.action='rooms.read' AND json_extract(projection_json,'$.entity')='room')); END;
    ''')


def get(conn,uid):
    found=rows(conn,'SELECT * FROM telegram_reminder_preference WHERE user_id=?',(uid,))
    return found[0] if found else {'user_id':uid,'calendar_minutes':0,'room_minutes':0,'revision':0}


def fence(conn,uid,entity=None):
    conn.execute('''UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
        claim_token=NULL,lease_until=NULL,error_code='reminder_preference'
        WHERE dedupe_key LIKE 'reminder:%' AND connection_id IN (SELECT id FROM telegram_connection WHERE account_id=?)
          AND state IN ('queued','claimed','retry_wait','sending')
          AND (? IS NULL OR json_extract(projection_json,'$.entity')=?)''',(uid,entity,entity))


def preference_changed(conn,uid,current,values):
    for entity in ('calendar','room'):
        if not preferences.MODES[values[entity+'_mode']][1]:fence(conn,uid,entity)
    if (current['quiet_start'] or '',current['quiet_end'] or '')!=(values['quiet_start'],values['quiet_end']):
        conn.execute('''UPDATE telegram_delivery SET not_before=NULL WHERE dedupe_key LIKE 'reminder:%'
            AND connection_id IN (SELECT id FROM telegram_connection WHERE account_id=?)
            AND state IN ('queued','claimed','retry_wait')''',(uid,))
        # Fence in-flight work as uncertain, while ordinary queued work is deferred.
        conn.execute('''UPDATE telegram_delivery SET state='uncertain',claim_token=NULL,lease_until=NULL,error_code='reminder_quiet_changed'
            WHERE dedupe_key LIKE 'reminder:%' AND state='sending'
            AND connection_id IN (SELECT id FROM telegram_connection WHERE account_id=?)''',(uid,))


def save(conn,payload,revision,calendar_minutes,room_minutes,now):
    import storage as st
    if (not re.fullmatch('[0-9]{1,18}',str(revision))
            or str(calendar_minutes) not in {str(n) for n in LEADS} or str(room_minutes) not in {str(n) for n in LEADS}):
        raise ValueError('Choose a listed reminder lead time and reload if the form expired.')
    with transaction(conn):
        user=links.current(conn,payload);old=get(conn,user['id'])
        if old['revision']!=int(revision):raise preferences.Conflict('Reminder settings changed. Review and save again.')
        for entity,minutes in (('calendar',int(calendar_minutes)),('room',int(room_minutes))):
            if old[entity+'_minutes']!=minutes:fence(conn,user['id'],entity)
        conn.execute('''INSERT INTO telegram_reminder_preference(user_id,calendar_minutes,room_minutes,revision)
            VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET calendar_minutes=excluded.calendar_minutes,
            room_minutes=excluded.room_minutes,revision=excluded.revision,calendar_after=0,room_after=0''',
            (user['id'],int(calendar_minutes),int(room_minutes),old['revision']+1))
        st.audit(conn,user['username'],'telegram_reminder_preferences',target_type='admin_user',target_id=user['id'],
                 summary='Updated private Telegram reminder choices.',after='revision='+str(old['revision']+1),commit=False)


def enabled():return all(switches.enabled(k) for k in ('inbound','delivery','link','reminders')) and links.available()


def source(conn,entity,identifier,user,occurrence):
    """Current owned occurrence, using normal calendar visibility and stored room slots."""
    import office_calendar as calendar
    import recurrence
    import rooms
    if entity=='calendar':
        record=calendar.viewable_entry(conn,user,identifier)
        if (not record or record['event_id'] or record['status']!='confirmed' or not record['start_time']
                or not (record['created_by']==user['username'] or any(p['user_id']==user['id'] for p in record['people']))):return None
        day=date.fromisoformat(occurrence)
        if day not in recurrence.occurrences(date.fromisoformat(record['start_date']),record['rrule'],record['exdates'],day,day):return None
        start=datetime.combine(day,time.fromisoformat(record['start_time']),common.ZONE)
    else:
        record=rooms.get_reservation(conn,identifier)
        if not record or record['status']!='approved' or record['requester_user_id']!=user['id'] or record['day']!=occurrence:return None
        first=conn.execute('''SELECT MIN(s.start_time) FROM room_reservation_slot rs JOIN room_slot s ON s.id=rs.slot_id
            WHERE rs.reservation_id=?''',(identifier,)).fetchone()[0]
        if not first:return None
        start=datetime.combine(date.fromisoformat(record['day']),time.fromisoformat(first),common.ZONE)
    return record,start.astimezone(timezone.utc)


def key(uid,entity,incarnation,start):
    return hashlib.sha256(json.dumps([uid,entity,incarnation,links.stamp(start)],separators=(',',':')).encode()).hexdigest()


def descriptor(p,bot):
    valid=(isinstance(p,dict) and set(p)=={'kind','entity','source','incarnation','occurrence','minutes','bot','fingerprint','key'}
        and p['kind']==KIND and p['entity'] in ('calendar','room') and type(p['source']) is int and p['source']>0
        and isinstance(p['incarnation'],str) and re.fullmatch('[a-f0-9]{32}',p['incarnation']) is not None
        and isinstance(p['occurrence'],str) and re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',p['occurrence']) is not None
        and type(p['minutes']) is int and p['minutes'] in LEADS[1:] and p['bot']==bot[0] and p['fingerprint']==bot[2]
        and isinstance(p['key'],str) and re.fullmatch('[a-f0-9]{64}',p['key']) is not None)
    if not valid:return False
    try:date.fromisoformat(p['occurrence']);return True
    except ValueError:return False


def allowed(conn,delivery,p,bot,now,*,respect_quiet=True):
    import telegram_notices as notices
    if not enabled() or not descriptor(p,bot):return None
    user=common.actor(conn,delivery,bot,action='calendar.read' if p['entity']=='calendar' else 'rooms.read')
    if not user:return None
    connection=conn.execute('SELECT bot_identity,bot_fingerprint FROM telegram_connection WHERE id=?',(delivery['connection_id'],)).fetchone()
    if tuple(connection)!=(bot[0],bot[2]):return None
    setting=get(conn,user['id']);pref=preferences.get(conn,user['id'])
    if setting[p['entity']+'_minutes']!=p['minutes'] or not pref[p['entity']+'_telegram']:return None
    if respect_quiet and preferences.quiet_until(pref,now):return None
    head=conn.execute('SELECT incarnation,revision,deleted FROM telegram_change_head WHERE entity=? AND source_id=?',(p['entity'],p['source'])).fetchone()
    if not head or head[0]!=p['incarnation'] or head[2]:return None
    found=source(conn,p['entity'],p['source'],user,p['occurrence'])
    if not found:return None
    record,start=found;k=key(user['id'],p['entity'],head[0],start)
    if (p['key']!=k or delivery['dedupe_key']!='reminder:'+k or delivery['event_key']!=k
            or delivery['expires_at']!=links.stamp(start) or not start-timedelta(minutes=p['minutes'])<=now<start
            or not conn.execute('SELECT 1 FROM telegram_reminder_occurrence WHERE occurrence_key=?',(k,)).fetchone()):return None
    route={**delivery,'topic_id':0,'bot_fingerprint':bot[2]}
    if notices.paused(conn,route):return None
    return record,start


def enqueue(conn,now):
    import storage as st
    import recurrence
    if not enabled():return 0
    count=0
    with transaction(conn):
        bot=transport.config()
        if not bot or not enabled():return 0
        after=int(st.get_setting(conn,'telegram_reminder_after') or 0)
        sql='SELECT * FROM telegram_reminder_preference WHERE user_id>? AND (calendar_minutes>0 OR room_minutes>0) ORDER BY user_id LIMIT ?'
        users=rows(conn,sql,(after,USERS_PER_TICK)) or rows(conn,sql,(0,USERS_PER_TICK))
        conn.execute("UPDATE app_setting SET value=? WHERE key='telegram_reminder_after'",(str(users[-1]['user_id'] if len(users)==USERS_PER_TICK else 0),))
        today=now.astimezone(common.ZONE).date();tomorrow=today+timedelta(days=1)
        for setting in users:
            found=rows(conn,"SELECT * FROM telegram_connection WHERE account_id=? AND state='active'",(setting['user_id'],))
            if not found:continue
            connection=found[0]
            if (connection['bot_identity'],connection['bot_fingerprint'])!=(bot[0],bot[2]):continue
            delivery={'connection_id':connection['id'],'generation':connection['generation'],'chat_id':connection['private_chat_id'],
                      'topic_id':None,'registration_id':None,'registration_generation':None}
            for entity,table in (('calendar','calendar_entry'),('room','room_reservation')):
                minutes=setting[entity+'_minutes']
                user=common.actor(conn,delivery,bot,action='calendar.read' if entity=='calendar' else 'rooms.read')
                if not minutes or not user or not preferences.get(conn,user['id'])[entity+'_telegram']:continue
                if entity=='calendar':
                    query='''SELECT id FROM calendar_entry WHERE id>? AND event_id IS NULL AND status='confirmed' AND start_time IS NOT NULL
                        AND start_date<=? AND (start_date>=? OR rrule IS NOT NULL)
                        AND (created_by=? OR EXISTS(SELECT 1 FROM calendar_entry_person p WHERE p.entry_id=calendar_entry.id AND p.user_id=?)) ORDER BY id LIMIT ?'''
                    args=(setting['calendar_after'],tomorrow.isoformat(),today.isoformat(),user['username'],user['id'],SOURCES_PER_USER)
                else:
                    query="SELECT id FROM room_reservation WHERE id>? AND requester_user_id=? AND status='approved' AND day BETWEEN ? AND ? ORDER BY id LIMIT ?"
                    args=(setting['room_after'],user['id'],today.isoformat(),tomorrow.isoformat(),SOURCES_PER_USER)
                candidates=rows(conn,query,args)
                conn.execute('UPDATE telegram_reminder_preference SET '+entity+'_after=? WHERE user_id=?',
                             (candidates[-1]['id'] if len(candidates)==SOURCES_PER_USER else 0,user['id']))
                for candidate in candidates:
                    identifier=candidate['id']
                    if entity=='calendar':
                        record=st.cal_get(conn,identifier)
                        days=recurrence.occurrences(date.fromisoformat(record['start_date']),record['rrule'],record['exdates'],today,tomorrow)
                    else:days=[date.fromisoformat(conn.execute('SELECT day FROM room_reservation WHERE id=?',(identifier,)).fetchone()[0])]
                    for day in days:
                        current=source(conn,entity,identifier,user,day.isoformat())
                        if not current:continue
                        record,start=current
                        if not start-timedelta(minutes=minutes)<=now<start:continue
                        head=conn.execute('SELECT incarnation FROM telegram_change_head WHERE entity=? AND source_id=?',(entity,identifier)).fetchone()
                        if not head:continue
                        k=key(user['id'],entity,head[0],start)
                        if not conn.execute('INSERT OR IGNORE INTO telegram_reminder_occurrence VALUES(?,?)',(k,links.stamp(now))).rowcount:continue
                        p={'kind':KIND,'entity':entity,'source':identifier,'incarnation':head[0],'occurrence':day.isoformat(),
                           'minutes':minutes,'bot':bot[0],'fingerprint':bot[2],'key':k}
                        due=preferences.quiet_until(preferences.get(conn,user['id']),now)
                        conn.execute('''INSERT INTO telegram_delivery(dedupe_key,event_key,connection_id,generation,chat_id,
                            projection_json,expires_at,created_at,updated_at,not_before,state)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)''',('reminder:'+k,k,connection['id'],connection['generation'],connection['private_chat_id'],
                            json.dumps(p,sort_keys=True),links.stamp(start),links.stamp(now),links.stamp(now),links.stamp(due) if due else None,
                            'cancelled' if due and due>=start else 'queued'))
                        count+=1
    return count


def defer(conn,delivery,bot,now):
    try:p=json.loads(delivery['projection_json'])
    except (TypeError,ValueError):return False
    if not allowed(conn,delivery,p,bot,now,respect_quiet=False):return False
    uid=conn.execute('SELECT account_id FROM telegram_connection WHERE id=?',(delivery['connection_id'],)).fetchone()[0]
    due=preferences.quiet_until(preferences.get(conn,uid),now)
    if not due:return False
    conn.execute('''UPDATE telegram_delivery SET not_before=?,state=CASE WHEN ? >= expires_at THEN 'cancelled'
        WHEN state='claimed' THEN 'queued' ELSE state END,claim_token=NULL,lease_until=NULL WHERE id=?''',
        (links.stamp(due),links.stamp(due),delivery['id']))
    return True


def render(conn,delivery,p,bot,now):
    import rooms
    import telegram_group_reads as shared
    with transaction(conn):
        found=allowed(conn,delivery,p,bot,now)
        if not found:return None
        record,start=found
        if p['entity']=='calendar':
            end=(date.fromisoformat(p['occurrence'])+(date.fromisoformat(record['end_date'] or record['start_date'])-date.fromisoformat(record['start_date']))).isoformat()
            record={**record,'start_date':p['occurrence'],'end_date':end}
            return 'Calendar reminder · upcoming occurrence\n'+shared.fields(record)+'\n'+links.origin()+'/calendar/entries/'+str(p['source'])+'?date='+p['occurrence']
        return ('Room booking reminder · approved (booked)\n'+common.clip(record['ref_code'],80)+' · '+record['day']
                +' · Asia/Manila\nBooked hours: '+common.clip(rooms.hours_text(conn,record),400)+'\n'+links.origin()+'/rooms/mine')


def cleanup_in_transaction(conn,now):
    conn.execute('''UPDATE telegram_delivery SET state='cancelled',claim_token=NULL,lease_until=NULL,error_code='reminder_expired'
        WHERE id IN (SELECT id FROM telegram_delivery WHERE dedupe_key LIKE 'reminder:%'
          AND state IN ('queued','claimed','retry_wait') AND expires_at<=? LIMIT 20)''',(links.stamp(now),))
    # Occurrence hashes contain no source, account, destination, content or grants;
    # retain them after the ordinary 180-day delivery purge to prevent replay.
