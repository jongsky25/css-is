"""Ephemeral private metadata search; every source keeps its existing read policy."""
from datetime import timedelta
import unicodedata

import documents_permissions as permissions
from documents_storage import rows
import office_calendar
import telegram_calendar as common
import telegram_links as links
import telegram_menu as menu

COMMANDS = ('/find',)
USAGE = 'Use /find WORDS (up to 80 characters). Search titles, document numbers and subjects; meetings cover the next 31 days.'


def parse(text):
    parts = text.split(maxsplit=1)
    term = parts[1].strip() if len(parts)==2 else ''
    if (not parts or parts[0]!='/find' or not term or len(term)>80
            or any(unicodedata.category(ch).startswith('C') for ch in term)):
        raise ValueError(USAGE)
    return {'term': term}


def actor(conn, delivery, bot):
    return menu.user(conn, delivery, bot)


def section(title, entries, more=False):
    return (title+'\n'+('\n\n'.join(entries) if entries else 'No matching permitted records.')
            + ('\nMore matches available; narrow your search.' if more else ''))


def render(conn, clean, bot, now):
    if not conn.in_transaction:
        raise RuntimeError('Private search requires the intake transaction')
    found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not found:
        return None
    link=found[0]
    context=dict(connection_id=link['id'],generation=link['generation'],chat_id=clean['chat_id'],
                 topic_id=clean['topic_id'],registration_id=None)
    user=actor(conn,context,bot)
    if not user:
        return None
    query=clean['search_query']
    if query=={'error':'usage'}:
        return USAGE
    ready={f['scope'] for f in menu.availability(conn,context,bot) if not f['reason']}
    term=query['term'].casefold()
    conn.create_function('telegram_find_casefold',1,lambda value:str(value or '').casefold(),deterministic=True)
    sections=[]
    if 'work.read' in ready:
        scope=permissions.RegistryScope(conn,user)
        params={**scope.params,'term':term}
        # Visibility and ownership precede matching and LIMIT. No outputs/notes.
        tasks=rows(conn,f'''SELECT t.id,t.case_id,t.title,t.status,t.due_date
            FROM work_task t JOIN work_case wc ON wc.id=t.case_id
            WHERE t.owner_id=:registry_actor AND {scope.work_view_sql('wc')}
            AND instr(telegram_find_casefold(t.title),:term)>0 ORDER BY t.id DESC LIMIT 3''',params)
        sections.append(section('My tasks · newest matches',[
            'Task '+str(t['id'])+' · '+common.clip(t['title'],80)
            +'\nStatus: '+common.clip(t['status'],32).replace('_',' ')+' · Due: '+common.clip(t['due_date'] or 'not set',32)
            +'\n/task_status '+str(t['case_id'])+' '+str(t['id']) for t in tasks[:2]],len(tasks)>2))
        cases=rows(conn,f'''SELECT wc.id,wc.title,wc.due_date FROM work_case wc
            WHERE {scope.work_view_sql('wc')} AND instr(telegram_find_casefold(wc.title),:term)>0
            ORDER BY wc.id DESC LIMIT 3''',params)
        # There is no authoritative overall work status. Show its due date.
        sections.append(section('Work items · newest matches',[
            'Work '+str(w['id'])+' · '+common.clip(w['title'],80)+'\nDue: '+common.clip(w['due_date'] or 'not set',32)
            +'\n/work_status '+str(w['id']) for w in cases[:2]],len(cases)>2))
    if 'documents.read' in ready:
        scope=permissions.RegistryScope(conn,user)
        docs=rows(conn,f'''SELECT d.id,d.number,d.subject,d.status FROM document d
            WHERE d.canonical_id IS NULL AND d.archived_at IS NULL AND {scope.view_sql('d')}
            AND instr(telegram_find_casefold(d.number || ' ' || d.subject),:term)>0
            ORDER BY d.id DESC LIMIT 3''',{**scope.params,'term':term})
        sections.append(section('Documents · newest matches',[
            'Document '+str(d['id'])+' · '+common.clip(d['number'],40)+' · '+common.clip(d['subject'],80)
            +'\nWorkflow: '+common.clip(d['status'],32).replace('_',' ')+'\n/document_status '+str(d['id']) for d in docs[:2]],len(docs)>2))
    if 'calendar.read' in ready:
        today=now.astimezone(common.ZONE).date();end=today+timedelta(days=30)
        items=office_calendar.items_between(conn,user,today.isoformat(),end.isoformat(),scope='blend',
                                           layers=('entries',),filters={'kinds':{'meeting'}})
        # Canonical visibility/recurrence expansion runs before title matching.
        matches=[item for item in items if term in item['title'].casefold()]
        entries=[]
        for item in matches[:2]:
            p=common.project(item,links.origin())
            entries.append(common.clip(p['title'],80)+' · '+p['status']+'\n'+p['start']+' · '
                           +('all day' if p['all_day'] else p['start_time'] or 'time not set')
                           +'\n/calendar '+p['start']+'\n'+p['url'])
        sections.append(section('Meetings · '+today.isoformat()+' through '+end.isoformat()+' · Asia/Manila',entries,len(matches)>2))
    text='Office Connect · private search'
    for result in sections:
        if common.units(text+'\n\n'+result)>3500:
            text+='\nMore results are available through the source commands in /menu.'
            break
        text+='\n\n'+result
    if not sections:
        text+='\nNo search sources are currently enabled and consented. Use /status to review availability.'
    return (text+'\n\nOnly currently permitted metadata is searched. Read only.'
            +'\nUse the displayed detail commands or narrow your search. /menu for source lookups.')
