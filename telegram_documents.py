"""Private webhook-only document metadata lookup; no retained search text."""
import re
import unicodedata

import documents
import documents_permissions as permissions
from documents_storage import rows
import telegram_calendar as common
import telegram_links as links
import work

COMMANDS = ('/documents', '/find_documents', '/document_status')
USAGE = 'Use /documents [BEFORE_ID], /find_documents WORDS (number or subject, up to 80 characters), or /document_status DOCUMENT_ID.'


def parse(text):
    parts = text.split(maxsplit=1)
    if not parts or parts[0] not in COMMANDS:
        raise ValueError(USAGE)
    command = parts[0]
    argument = parts[1].strip() if len(parts) == 2 else ''
    if command == '/find_documents':
        if not argument or len(argument)>80 or any(unicodedata.category(ch).startswith('C') for ch in argument):
            raise ValueError(USAGE)
        return {'command': command, 'query': argument}
    if not argument and command=='/documents':
        return {'command': command, 'before': 0}
    if not re.fullmatch('[1-9][0-9]{0,18}', argument) or int(argument)>9223372036854775807:
        raise ValueError(USAGE)
    return {'command': command, 'before' if command=='/documents' else 'id': int(argument)}


def actor(conn, delivery, bot):
    user = common.actor(conn, delivery, bot, action='documents.read')
    return user if user and documents.enabled(conn) else None


def line(row):
    return ('Document '+str(row['id'])+' · '+common.clip(row['number'],50)+'\n'+common.clip(row['subject'],160)
            +'\nWorkflow: '+common.clip(row['status'],40).replace('_',' ')
            +' · Verification: '+common.clip(row['verification'],30)
            +'\nDue: '+common.clip(row['due_date'] or 'not set',32))


def render(conn, clean, bot, now):
    # Intake owns BEGIN IMMEDIATE, including authorization, reads and reply handoff.
    if not conn.in_transaction:
        raise RuntimeError('Document lookup requires the intake transaction')
    connection = rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not connection:
        return None
    link=connection[0]
    delivery={'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
              'topic_id':clean['topic_id'],'registration_id':None}
    user=actor(conn,delivery,bot)
    if not user:
        return None
    query=clean['document_query']
    if query=={'error':'usage'}:
        return USAGE
    scope=permissions.RegistryScope(conn,user)
    if query['command']=='/document_status':
        selected=rows(conn,f'SELECT d.* FROM document d WHERE d.id=:id AND {scope.view_sql("d")}',
                      {**scope.params,'id':query['id']})
        # Shared canonical resolver is cycle-safe and does not require work enabled.
        doc=work.resolved_document(conn,selected[0]['id']) if selected else None
        if not doc:
            return 'Document unavailable to this account.'
        text=line(doc)
        routing={'pending':'awaiting routing instruction','issued':'instruction issued','not_required':'no initial instruction required'}
        text+='\nRouting: '+routing.get(doc['instruction_state'],common.clip(doc['instruction_state'],40))
        text+='\nLead: '+('assigned' if doc['lead_id'] else 'not assigned')
        text+='\nReviewer: '+('assigned' if doc['reviewer_id'] else 'not assigned')
        text+='\nApproval: '+('current version approved' if doc['current_version'] and doc['approved_version']==doc['current_version'] else 'current version not recorded as approved')
        if doc['archived_at']:
            text+='\nArchived record'
        return text+'\nBack: /documents\n'+links.origin()+'/documents/'+str(doc['id'])
    # Canonical, non-archived records match the default signed-in registry.
    # Search is literal metadata-only: no FTS, bodies, senders or references.
    params={**scope.params,'before':query.get('before',0),'term':query.get('query','').casefold()}
    conn.create_function('telegram_doc_casefold',1,lambda s:str(s or '').casefold(),deterministic=True)
    records=rows(conn,f'''SELECT d.* FROM document d WHERE d.canonical_id IS NULL AND d.archived_at IS NULL
        AND {scope.view_sql('d')} AND (:before=0 OR d.id<:before)
        AND (:term='' OR instr(telegram_doc_casefold(d.number || ' ' || d.subject),:term)>0)
        ORDER BY d.id DESC LIMIT 6''',params)
    text='My accessible documents (newest first)'
    if query['command']=='/find_documents':
        text+='\nNumber and subject search'
    shown=[]
    for row in records[:5]:
        entry=line(row)+'\nDetails: /document_status '+str(row['id'])+'\n'+links.origin()+'/documents/'+str(row['id'])
        if common.units(text+'\n\n'+entry)>2900:
            break
        text+='\n\n'+entry;shown.append(row)
    if not records:
        text+='\nNo matching documents available to this account.'
    if shown and (len(records)>len(shown)):
        text+=('\nMore matches: narrow your search.' if query['command']=='/find_documents'
               else '\nNext page: /documents '+str(shown[-1]['id']))
    return text+'\n\nOpen Documents: '+links.origin()+'/documents'
