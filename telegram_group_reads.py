"""Explicit shared projections, independent of a requester's private calendar."""
import hashlib
import json
from datetime import date

from documents_storage import rows,transaction
import office_calendar
import rooms
import storage as st
import telegram_calendar as common
import telegram_links as links

USAGE='Use /group_calendar [YYYY-MM-DD [YYYY-MM-DD]] (maximum 31 days) or /group_rooms [YYYY-MM-DD]. Asia/Manila.'


def parse(text,now):
    parts=text.split();today=now.astimezone(common.ZONE).date().isoformat()
    if parts[0]=='/group_calendar' and len(parts) in (1,2,3):
        start=parts[1] if len(parts)>1 else today
        end=parts[2] if len(parts)>2 else start
        common.validate(start,end,'bureau')
        return {'mode':'calendar','start':start,'end':end}
    if parts[0]=='/group_rooms' and len(parts) in (1,2):
        day=parts[1] if len(parts)>1 else today
        common.validate(day,day,'bureau')
        return {'mode':'rooms','day':day}
    raise ValueError(USAGE)


def descriptor(projection,bot):
    if (not isinstance(projection,dict) or set(projection)!={'kind','bot','fingerprint','query'}
            or projection['kind']!='group_read' or projection['bot']!=bot[0] or projection['fingerprint']!=bot[2]):
        return False
    q=projection['query']
    try:
        if not isinstance(q,dict):
            return False
        if q in ({'error':'usage'},{'error':'usage','mode':'rooms'}):
            return True
        if q.get('mode')=='calendar' and set(q)=={'mode','start','end'}:
            common.validate(q['start'],q['end'],'bureau');return True
        if q.get('mode')=='rooms' and set(q)=={'mode','day'}:
            common.validate(q['day'],q['day'],'bureau');return True
    except (ValueError,TypeError):
        pass
    return False


def action(projection):
    return 'rooms.read' if projection['query'].get('mode')=='rooms' else 'calendar.read'


def shareable(conn,user,entry_id):
    entry=office_calendar.viewable_entry(conn,user,entry_id)
    # Linked activity overlays and recurrence need their own disclosure review.
    if (not entry or entry['audience']!='bureau' or entry.get('event_id') is not None
            or entry.get('rrule') or entry.get('cancelled_at')):
        return None
    return entry


def revision(entry):
    # Consent is for the exact source version, including unprojected source changes.
    return hashlib.sha256(json.dumps({k:entry[k] for k in st._CAL_COLS},sort_keys=True,default=str).encode()).hexdigest()


def fields(entry):
    return (common.clip(entry['title'],120)+'\n'+entry['start_date']+' – '+(entry['end_date'] or entry['start_date'])
            +' · '+common.clip(entry['start_time'] or 'all day',10)+' – '+common.clip(entry['end_time'] or '',10)
            +' · Asia/Manila\nVenue: '+common.clip(entry['venue'],80)+'\nStatus: '+common.clip(entry['status'],40))


def consent(conn,payload,group_id,generation,entry_id,expected,approve,now):
    import telegram_groups as groups
    with transaction(conn):
        user=links.current(conn,payload)
        found=rows(conn,'SELECT * FROM telegram_group WHERE id=?',(group_id,))
        if not found or found[0]['owner_account_id']!=user['id'] or found[0]['generation']!=generation:
            raise ValueError('Registration unavailable or changed. Reload and try again.')
        group=found[0]
        if approve:
            bot=groups.transport.config()
            if (not bot or not groups.route(conn,group['chat_id'],group['topic_id'],bot)
                    or not links.authorized(conn,user['id'],'calendar.read')):
                raise ValueError('A current group and calendar read consent are required.')
            entry=shareable(conn,user,entry_id)
            if not entry or revision(entry)!=expected:
                raise ValueError('Entry unavailable or changed. Preview it again.')
            conn.execute('''INSERT INTO telegram_group_share
                (entry_id,registration_id,registration_generation,revision,consented_by,consented_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(entry_id,registration_id) DO UPDATE SET
                registration_generation=excluded.registration_generation,revision=excluded.revision,
                consented_by=excluded.consented_by,consented_at=excluded.consented_at,revoked_at=NULL''',
                (entry_id,group_id,generation,expected,user['id'],links.stamp(now)))
        else:
            conn.execute('UPDATE telegram_group_share SET revoked_at=? WHERE entry_id=? AND registration_id=?',
                         (links.stamp(now),entry_id,group_id))
        st.audit(conn,user['username'],'telegram_group_share' if approve else 'telegram_group_unshare',
                 target_type='calendar_entry',target_id=entry_id,
                 summary='Approved or revoked exact-version Telegram group disclosure.',
                 after=json.dumps({'registration_id':group_id,'generation':generation,'revision':expected if approve else None}),commit=False)


def render(conn,delivery,projection,bot,now):
    import telegram_groups as groups
    with transaction(conn):
        authorized=groups.authorize_delivery(conn,delivery,bot)
        if not authorized or not descriptor(projection,bot):
            return None
        group,actor=authorized;q=projection['query']
        if q in ({'error':'usage'},{'error':'usage','mode':'rooms'}):
            return USAGE
        if q['mode']=='rooms':
            view=rooms.day_view(conn,date.fromisoformat(q['day']),today=now.astimezone(common.ZONE).date())
            text='Shared conference-room slots · Asia/Manila\n'+q['day']
            for slot in view['hours']:
                line=common.clip(slot['label'],80)+': '+slot['state']
                if common.units(text+'\n'+line)>2700:
                    text+='\nMore slots on the signed-in page.';break
                text+='\n'+line
            return text+'\nRequested is pending approval; no booking held. Current snapshot.\n'+links.origin()+'/rooms?day='+q['day']
        user={'id':actor['account_id'],'username':actor['username'],'role':actor['role']}
        candidates=rows(conn,'''SELECT e.id,s.revision FROM telegram_group_share s JOIN calendar_entry e ON e.id=s.entry_id
            WHERE s.registration_id=? AND s.registration_generation=? AND s.revoked_at IS NULL
            AND e.start_date<=? AND COALESCE(NULLIF(e.end_date,''),e.start_date)>=?
            ORDER BY e.start_date,e.start_time,e.id LIMIT 51''',(group['id'],group['generation'],q['end'],q['start']))
        text='Shared schedule · Asia/Manila\n'+q['start']+' – '+q['end'];shown=0
        for candidate in candidates[:50]:
            entry=shareable(conn,user,candidate['id'])
            if not entry or revision(entry)!=candidate['revision']:
                continue
            line=fields(entry)+'\n'+links.origin()+'/calendar/entries/'+str(entry['id'])
            if shown>=10 or common.units(text+'\n\n'+line)>3300:
                text+='\nMore shared entries: narrow the dates or open Office Connect.';break
            text+='\n\n'+line;shown+=1
        else:
            if len(candidates)>50:
                text+='\nMore shared entries: narrow the dates or open Office Connect.'
        if not shown:
            text+='\nNo approved shared entries in this range.'
        return text
