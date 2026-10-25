"""Self-service automatic-notice channels and explicit Manila quiet hours."""
from datetime import datetime,time,timedelta,timezone
import re
from zoneinfo import ZoneInfo

from documents_storage import rows,transaction

ZONE=ZoneInfo('Asia/Manila')
MODES={'off':(False,False),'email':(True,False),'telegram':(False,True),'both':(True,True)}


class Conflict(ValueError):pass


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS telegram_notification_preference(
      user_id INTEGER PRIMARY KEY REFERENCES admin_user(id) ON DELETE CASCADE,
      calendar_telegram INTEGER NOT NULL DEFAULT 1 CHECK(calendar_telegram IN (0,1)),
      room_telegram INTEGER NOT NULL DEFAULT 1 CHECK(room_telegram IN (0,1)),
      room_email INTEGER NOT NULL DEFAULT 1 CHECK(room_email IN (0,1)),
      group_calendar INTEGER NOT NULL DEFAULT 1 CHECK(group_calendar IN (0,1)),
      group_room INTEGER NOT NULL DEFAULT 1 CHECK(group_room IN (0,1)),
      quiet_start TEXT,quiet_end TEXT,revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),updated_at TEXT,
      CHECK((quiet_start IS NULL AND quiet_end IS NULL) OR
            (quiet_start IS NOT NULL AND quiet_end IS NOT NULL AND quiet_start<>quiet_end)));
    ''')
    if 'not_before' not in {r[1] for r in conn.execute('PRAGMA table_info(telegram_delivery)')}:
        conn.execute('ALTER TABLE telegram_delivery ADD COLUMN not_before TEXT')


def get(conn,user_id):
    import storage as st
    found=rows(conn,'SELECT * FROM telegram_notification_preference WHERE user_id=?',(user_id,))
    p=found[0] if found else {'user_id':user_id,'calendar_telegram':1,'room_telegram':1,'room_email':1,
                            'group_calendar':1,'group_room':1,'quiet_start':None,'quiet_end':None,'revision':0}
    p={**p,'calendar_email':st.calendar_email_pref(conn,user_id)}
    for prefix in ('calendar','room'):
        pair=(bool(p[prefix+'_email']),bool(p[prefix+'_telegram']))
        p[prefix+'_mode']=next(mode for mode,bits in MODES.items() if pair==bits)
    return p


def quiet_until(pref,now):
    if not pref['quiet_start'] or not pref['quiet_end']:return None
    local=now.replace(tzinfo=ZONE) if now.tzinfo is None else now.astimezone(ZONE)
    clock=local.strftime('%H:%M');start=pref['quiet_start'];end=pref['quiet_end']
    quiet=start<=clock<end if start<end else clock>=start or clock<end
    if not quiet:return None
    day=local.date()+timedelta(days=int(start>end and clock>=start))
    return datetime.combine(day,time.fromisoformat(end),ZONE).astimezone(timezone.utc)


def route_preferences(conn,route):
    if route['registration_id'] is not None:
        found=conn.execute('SELECT owner_account_id FROM telegram_group WHERE id=?',(route['registration_id'],)).fetchone()
    else:found=conn.execute('SELECT account_id FROM telegram_connection WHERE id=?',(route['connection_id'],)).fetchone()
    return get(conn,found[0]) if found else None


def telegram_enabled(conn,route):
    pref=route_preferences(conn,route)
    field={'calendar_private':'calendar_telegram','room_private':'room_telegram',
           'calendar_shared':'group_calendar','room_availability':'group_room'}.get(route['projection'])
    return bool(pref and field and pref[field])


def delay_until(conn,route,now):
    pref=route_preferences(conn,route)
    return quiet_until(pref,now) if pref else None


def _scope_sql():
    return '''(registration_id IS NULL AND connection_id IN (SELECT id FROM telegram_connection WHERE account_id=:uid))
        OR registration_id IN (SELECT id FROM telegram_group WHERE owner_account_id=:uid)'''


def save(conn,payload,revision,expected_email,values,now):
    import storage as st
    import telegram_links as links
    if (set(values)!={'calendar_mode','room_mode','group_calendar','group_room','quiet_start','quiet_end'}
            or not all(isinstance(values[k],str) for k in ('calendar_mode','room_mode'))
            or values['calendar_mode'] not in MODES or values['room_mode'] not in MODES
            or any(type(values[k]) is not bool for k in ('group_calendar','group_room'))
            or not re.fullmatch('[0-9]{1,18}',str(revision)) or str(expected_email) not in ('0','1')):
        raise ValueError('Choose valid notification channels and reload the form if it expired.')
    start=values['quiet_start'];end=values['quiet_end']
    if (not isinstance(start,str) or not isinstance(end,str) or bool(start)!=bool(end)
            or (start and (not all(re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',v) for v in (start,end)) or start==end))):
        raise ValueError('Choose both quiet-hour times in HH:MM, with different start and end, or leave both blank.')
    with transaction(conn):
        user=links.current(conn,payload);current=get(conn,user['id'])
        if current['revision']!=int(revision) or int(current['calendar_email'])!=int(expected_email):
            raise Conflict('Notification settings changed. Review the current values and save again.')
        calendar_email,calendar_telegram=MODES[values['calendar_mode']]
        room_email,room_telegram=MODES[values['room_mode']]
        args={'uid':user['id'],'calendar_telegram':int(calendar_telegram),'room_telegram':int(room_telegram),
              'room_email':int(room_email),'group_calendar':int(values['group_calendar']),'group_room':int(values['group_room']),
              'quiet_start':start or None,'quiet_end':end or None,'revision':current['revision']+1,'updated_at':links.stamp(now)}
        # One shared calendar-email setting: /me remains authoritative too.
        conn.execute('UPDATE admin_user SET cal_email_changes=? WHERE id=?',(None if calendar_email else 0,user['id']))
        conn.execute('''INSERT INTO telegram_notification_preference(user_id,calendar_telegram,room_telegram,room_email,
            group_calendar,group_room,quiet_start,quiet_end,revision,updated_at)
            VALUES(:uid,:calendar_telegram,:room_telegram,:room_email,:group_calendar,:group_room,:quiet_start,:quiet_end,:revision,:updated_at)
            ON CONFLICT(user_id) DO UPDATE SET calendar_telegram=excluded.calendar_telegram,room_telegram=excluded.room_telegram,
            room_email=excluded.room_email,group_calendar=excluded.group_calendar,group_room=excluded.group_room,
            quiet_start=excluded.quiet_start,quiet_end=excluded.quiet_end,revision=excluded.revision,updated_at=excluded.updated_at''',args)
        conn.execute('''UPDATE telegram_change_route SET state='cancelled',reason='notification_preference'
            WHERE state='prepared' AND ((connection_id IN (SELECT id FROM telegram_connection WHERE account_id=:uid)
              AND registration_id IS NULL AND ((projection='calendar_private' AND :calendar_telegram=0)
                OR (projection='room_private' AND :room_telegram=0)))
              OR (registration_id IN (SELECT id FROM telegram_group WHERE owner_account_id=:uid)
                AND ((projection='calendar_shared' AND :group_calendar=0) OR (projection='room_availability' AND :group_room=0))))''',args)
        # Quiet deferral is independent of retry_at: changing the window cannot
        # erase Telegram's minimum retry delay after a definite 429.
        if (current['quiet_start'],current['quiet_end'])!=(args['quiet_start'],args['quiet_end']):
            conn.execute("UPDATE telegram_delivery SET not_before=NULL WHERE state IN ('queued','claimed','retry_wait') AND dedupe_key IN (SELECT delivery_key FROM telegram_change_route WHERE "+_scope_sql()+')',args)
        st.audit(conn,user['username'],'telegram_notification_preferences',target_type='admin_user',target_id=user['id'],
                 summary='Updated calendar and room notification preferences.',after='revision='+str(args['revision']),commit=False)
