"""Private on-demand brief composed from current, separately permitted sources."""
from datetime import timedelta

from documents_storage import rows
import office_calendar
import rooms
import telegram_brief_preferences as preferences
import telegram_calendar as common
import telegram_links as links
import telegram_menu as menu
import telegram_personal as personal
import telegram_supplies as supplies
import telegram_work as work

COMMANDS = ('/brief',)
USAGE = 'Use /brief without arguments for your daily work brief.'


def actor(conn, delivery, bot):
    return menu.user(conn, delivery, bot)


def render(conn, clean, bot, now):
    if not conn.in_transaction:
        raise RuntimeError('Daily brief requires the intake transaction')
    found = rows(conn, "SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'", (clean['sender_id'],))
    if not found:
        return None
    link = found[0]
    context = dict(connection_id=link['id'], generation=link['generation'], chat_id=clean['chat_id'],
                   topic_id=clean['topic_id'], registration_id=None)
    user = actor(conn, context, bot)
    if not user:
        return None
    if clean['brief_query'] == {'error': 'usage'}:
        return USAGE
    ready = {f['scope'] for f in menu.availability(conn, context, bot) if not f['reason']}
    pref = preferences.get(conn, user['id'])
    today = now.astimezone(common.ZONE).date()
    end = today+timedelta(days=6)
    sections = []
    if pref['calendar'] and 'calendar.read' in ready:
        # Canonical calendar visibility, participation and recurrence expansion.
        items = office_calendar.items_between(conn, user, today.isoformat(), end.isoformat(),
                                             scope='mine', layers=('entries',))
        text = 'My calendar · '+today.isoformat()+' through '+end.isoformat()
        for item in items[:2]:
            p = common.project(item, links.origin())
            text += '\n'+p['start']+' · '+('all day' if p['all_day'] else p['start_time'] or 'time not set')
            text += ' · '+p['title']+' ['+p['status']+']'
        text += '\n'+(str(len(items))+' entries in range.' if items else 'No entries in range.')
        sections.append(text+'\n/calendar '+today.isoformat()+' '+end.isoformat()+' mine')
    if pref['work'] and 'work.read' in ready:
        # Source RegistryScope excludes hidden linked documents before counting.
        sections.append(work.summary(conn, user, now).split('\nCounts use current permitted records.')[0])
    if pref['requests'] and 'rooms.read' in ready:
        records = rooms.list_for_user(conn, user['id'], start=today.isoformat(), end=end.isoformat(), limit=3)
        text = 'My room requests · next seven days'
        for r in records[:2]:
            status = 'requested (not booked)' if r['status']=='requested' else r['status']
            text += '\n'+common.clip(r['ref_code'],40)+' · '+common.clip(status,60)+' · /room_status '+common.clip(r['ref_code'],40)
        sections.append(text+('\nMore available.' if len(records)>2 else '\nNo requests in range.' if not records else '')+'\n/my_rooms '+today.isoformat()+' '+end.isoformat())
    if pref['requests'] and 'supplies.read' in ready:
        result = supplies.dashboard.queue(conn, user, 'requests', state='needs_action', limit=2)
        text = 'My supplies needing action: '+str(result['total'])
        for r in result['requests']:
            text += '\nRequest '+str(r['id'])+' · '+common.clip(r['stage']['label'],60)+' · /supply_status '+str(r['id'])
        sections.append(text+'\n/my_supplies needs_action')
    if pref['requests']:
        for adapter, command, label in (
                (personal.TRAVEL, '/my_travel', 'Recent travel filings'),
                (personal.MEALS, '/my_meals', 'Recent meal requests'),
                (personal.MEALS, '/my_room_meals', 'Recent room-linked meals'),
                (personal.ARRANGEMENTS, '/my_arrangements', 'Recent arrangement filings')):
            if adapter.scope not in ready:
                continue
            table, owner, extra = adapter.source(command)
            records = rows(conn, f'SELECT q.* FROM {table} WHERE {owner}=? AND ({extra}) ORDER BY q.id DESC LIMIT 2', (user['id'],))
            text = label+' · newest two (all statuses)'
            for r in records:
                detail = '/room_meal_status' if command=='/my_room_meals' else adapter.COMMANDS[1]
                text += '\n'+str(r['id'])+' · '+common.clip(r['status'],40)+' · '+detail+' '+str(r['id'])
            sections.append(text+('\nNo records.' if not records else '')+'\n'+command)
    text = 'My daily brief · Asia/Manila · '+today.isoformat()
    for section in sections:
        # Each section is complete; never cut a command or a Unicode character.
        if common.units(text+'\n\n'+section)>3300:
            text += '\nMore sections are available through /menu.'
            break
        text += '\n\n'+section
    if not sections:
        text += '\nNo selected sections are currently enabled and consented. Use /status to review availability.'
    return (text+'\n\nCurrent permitted records only; this summary does not approve or change anything.'
            +'\nBrief choices: '+links.origin()+'/account/telegram/notifications'
            +'\nScheduled daily brief delivery is not active. /menu for full results.')
