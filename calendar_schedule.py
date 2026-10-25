"""Read-only FullCalendar snapshot over items already authorized by office_calendar."""
from datetime import date, datetime, time, timedelta
import tzutil as tz

MAX_ITEMS = 500


def snapshot(items, start, end, today, selected):
    zone = tz.LOCAL_TZ.tzname(None)
    label = ('Philippine time' if tz.LOCAL_TZ.utcoffset(None) == timedelta(hours=8)
             else 'Office time') + f' ({zone})'
    out = {'available': False, 'reason': '', 'zone': zone, 'label': label,
           'days': [{'date': (start + timedelta(days=n)).isoformat(),
                     'label': (start + timedelta(days=n)).strftime('%a, %b %d')}
                    for n in range((end-start).days+1)],
           'selected': selected.isoformat(), 'start': start.isoformat(),
           'today': today.isoformat(), 'events': []}
    if len(items) > MAX_ITEMS:
        out['reason'] = f'The hour grid supports up to {MAX_ITEMS} items per week. Narrow the filters or use the complete list below.'
        return out
    try:
        out['end'] = (end + timedelta(days=1)).isoformat()
        out['events'] = [_event(item) for item in items]
    except (ValueError, TypeError, KeyError, OverflowError):
        out['events'] = []
        out['reason'] = 'Some dates need review. Use the complete weekly list below.'
        return out
    out['available'] = True
    return out


def _event(item):
    start = date.fromisoformat(item['start'])
    end = date.fromisoformat(item['end'])
    if end < start:
        raise ValueError('invalid interval')
    clock_start, clock_end = item.get('start_time'), item.get('end_time')
    timed = not item.get('all_day', True) and bool(clock_start and clock_end)
    if timed:
        a, b = time.fromisoformat(clock_start), time.fromisoformat(clock_end)
        if a.tzinfo or b.tzinfo:
            raise ValueError('expected office wall time')
        a = datetime.combine(start, a, tzinfo=tz.LOCAL_TZ)
        b = datetime.combine(end, b, tzinfo=tz.LOCAL_TZ)
        if b <= a:
            raise ValueError('invalid timed interval')
        first, last = a.isoformat(), b.isoformat()
    else:
        first, last = start.isoformat(), (end + timedelta(days=1)).isoformat()
    note = str(item.get('time_note') or '')
    if not note:
        note = (f'{clock_start} · End time not set' if clock_start and not clock_end
                else f'Ends {clock_end} · Start time not set' if clock_end and not clock_start
                else 'All-day / time not set')
    href = str(item.get('url') or '')
    if (not href.startswith('/') or href.startswith('//') or '\\' in href
            or any(ord(c) < 33 for c in href)):
        href = ''
    return {'id': str(item['key']), 'title': str(item['title']),
            'start': first, 'end': last, 'allDay': not timed,
            'extendedProps': {'href': href, 'owner': str(item.get('owner_label') or ''),
                              'status': str(item.get('status') or 'confirmed').capitalize(),
                              'tone': str(item.get('tone') or 'grey'), 'timeLabel': note}}
