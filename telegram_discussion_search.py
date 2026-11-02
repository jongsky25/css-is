"""Consent-gated literal current-discussion search; queries and excerpts stay ephemeral."""
import os
import re
import unicodedata

from documents_storage import rows
import telegram_calendar as common
import telegram_links as links
import telegram_storage as switches
import work
import work_discussion as discussion

ACTION='work.discussion.search'
COMMANDS=('/discussion_search',)
USAGE='Use /discussion_search WORK_ID work|TASK_ID [before:COMMENT_ID] WORDS. Search a 2–80 character literal phrase in one current discussion; excerpts appear in this private Telegram chat.'
DENIED='Discussion unavailable to this account. Open Office Connect to check current access.'
PAGE_SIZE=3
EXCERPT_LIMIT=240


def number(value):
    if not re.fullmatch('[1-9][0-9]{0,18}',value) or int(value)>9223372036854775807:raise ValueError(USAGE)
    return int(value)


def parse(text):
    parts=text.split(maxsplit=3)
    if len(parts)!=4 or parts[0] not in COMMANDS:raise ValueError(USAGE)
    case_id=number(parts[1]);task_id=None if parts[2]=='work' else number(parts[2])
    term=parts[3].strip();before=0
    if term.startswith('before:'):
        token,separator,term=term.partition(' ')
        if not separator:raise ValueError(USAGE)
        before=number(token[len('before:'):]);term=term.strip()
    if not 2<=len(term)<=80 or any(unicodedata.category(ch).startswith('C') for ch in term):raise ValueError(USAGE)
    return {'case_id':case_id,'task_id':task_id,'before':before,'term':term}


def actor(conn,delivery,bot):
    user=common.actor(conn,delivery,bot,action=ACTION)
    return user if (user and work.enabled(conn) and links.authorized(conn,user['id'],'work.read')
                    and switches.enabled('inbound') and switches.enabled('delivery')
                    and os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT')!='direct') else None


def excerpt(body,term):
    """Bound an original-text window around a Unicode-casefold match, including expansions."""
    body=str(body or '');folded=body.casefold();needle=term.casefold();position=folded.find(needle)
    if position<0:return ''
    offsets=[i for i,ch in enumerate(body) for _ in ch.casefold()]
    first=offsets[position];last=offsets[position+len(needle)-1]+1
    start=max(0,first-60)
    if last>start+EXCERPT_LIMIT:start=max(0,last-EXCERPT_LIMIT)
    end=min(len(body),start+EXCERPT_LIMIT)
    return ('…' if start else '')+common.clip(body[start:end],EXCERPT_LIMIT)+('…' if end<len(body) else '')


def page(conn,user,query):
    # Native work/every-document and exact-thread permission checks precede any body SQL.
    _,item,task=discussion.scope(conn,user,query['case_id'],query['task_id'])
    conn.create_function('telegram_discussion_casefold',1,lambda value:str(value or '').casefold(),deterministic=True)
    conn.create_function('telegram_discussion_excerpt',2,excerpt,deterministic=True)
    found=rows(conn,'''SELECT c.id,c.parent_id IS NOT NULL AS is_reply,r.revision,
        telegram_discussion_excerpt(r.body,:term) AS excerpt
        FROM work_comment c JOIN work_comment_revision r ON r.comment_id=c.id
          AND r.revision=(SELECT MAX(v.revision) FROM work_comment_revision v WHERE v.comment_id=c.id)
        WHERE c.case_id=:case_id AND c.task_id IS :task_id AND (:before=0 OR c.id<:before)
          AND instr(telegram_discussion_casefold(r.body),:folded)>0
        ORDER BY c.id DESC LIMIT :limit''',
        {**query,'folded':query['term'].casefold(),'limit':PAGE_SIZE+1})
    return item,task,found


def source(case_id,task_id,comment_id):
    return (links.origin()+'/work/'+str(case_id)+'/discussion?focus='+str(comment_id)
            +('&task_id='+str(task_id) if task_id is not None else '')+'#message-'+str(comment_id))


def render(conn,clean,bot,now):
    if not conn.in_transaction:raise RuntimeError('Discussion search requires the intake transaction')
    found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not found:return None
    link=found[0];context={'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
                         'topic_id':clean['topic_id'],'registration_id':None}
    user=actor(conn,context,bot)
    if not user:return None
    query=clean['discussion_search_query']
    if query=={'error':'usage'}:return USAGE
    try:item,task,matches=page(conn,user,query)
    except ValueError:return DENIED
    text=('Discussion search · current revisions · newest comment ID first\nWork '+str(item['id'])+' · '+common.clip(item['title'],110)
          +('\nTask '+str(task['id'])+' · '+common.clip(task['title'],110) if task else '\nWork-level discussion only; task threads are searched separately.'))
    shown=[]
    for match in matches[:PAGE_SIZE]:
        block=(('Reply' if match['is_reply'] else 'Comment')+' '+str(match['id'])+' · Revision '+str(match['revision'])
               +'\nExcerpt: '+match['excerpt']+'\n'+source(item['id'],query['task_id'],match['id']))
        if common.units(text+'\n\n'+block)>3000:break
        text+='\n\n'+block;shown.append(match)
    if not shown:text+='\nNo current matching comments or replies in this permitted discussion.'
    if shown and len(shown)<len(matches):
        text+='\nNext page: /discussion_search '+str(item['id'])+' '+(str(task['id']) if task else 'work')+' before:'+str(shown[-1]['id'])+' '+query['term']
    return (text+'\nLimited excerpts are copied to this private Telegram chat. Read the full current discussion in Office Connect.'
            +'\nSearch marks nothing read and changes no records or preferences. Earlier revisions and other threads are excluded; no hidden counts are shown.')
