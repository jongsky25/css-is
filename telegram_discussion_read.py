"""Private top-level browsing, selected replies and revision-bound message parts."""
import os
import re
import unicodedata

from documents_storage import rows
import telegram_calendar as common
import telegram_links as links
import telegram_storage as switches
import work
import work_discussion as discussion

ACTION='work.discussion.read'
COMMANDS=('/discussion_thread','/discussion_message','/discussion_browse')
USAGE='Use /discussion_browse WORK_ID work|TASK_ID [before:COMMENT_ID], /discussion_thread WORK_ID work|TASK_ID COMMENT_ID [before:REPLY_ID], or /discussion_message WORK_ID work|TASK_ID COMMENT_ID [part:REVISION:NUMBER]. Current text is copied into this private chat; read status stays unchanged.'
DENIED='Discussion message unavailable to this account. Open Office Connect to check current source access.'
PAGE_SIZE=3
ROOT_PREVIEW=300
REPLY_PREVIEW=180
PART_SIZE=900
MAX_PARTS=5


def number(value):
    if not re.fullmatch('[1-9][0-9]{0,18}',value) or int(value)>9223372036854775807:raise ValueError(USAGE)
    return int(value)


def parse(text):
    parts=text.split()
    if parts and parts[0]=='/discussion_browse':
        if len(parts) not in (3,4):raise ValueError(USAGE)
        query={'command':parts[0],'case_id':number(parts[1]),'task_id':None if parts[2]=='work' else number(parts[2]),'before':0}
        if len(parts)==4:
            if not parts[3].startswith('before:'):raise ValueError(USAGE)
            query['before']=number(parts[3][7:])
        return query
    if len(parts) not in (4,5) or parts[0] not in COMMANDS:raise ValueError(USAGE)
    query={'command':parts[0],'case_id':number(parts[1]),'task_id':None if parts[2]=='work' else number(parts[2]),'comment_id':number(parts[3])}
    if parts[0]=='/discussion_thread':
        query['before']=0
        if len(parts)==5:
            if not parts[4].startswith('before:'):raise ValueError(USAGE)
            query['before']=number(parts[4][len('before:'):])
    else:
        query.update(revision=0,part=1)
        if len(parts)==5:
            if not re.fullmatch('part:[1-9][0-9]{0,18}:[1-9][0-9]*',parts[4]):raise ValueError(USAGE)
            _,revision,part=parts[4].split(':');query.update(revision=number(revision),part=number(part))
            if query['part']>MAX_PARTS:raise ValueError(USAGE)
    return query


def actor(conn,delivery,bot):
    user=common.actor(conn,delivery,bot,action=ACTION)
    return user if (user and work.enabled(conn) and links.authorized(conn,user['id'],'work.read')
                    and switches.enabled('inbound') and switches.enabled('delivery')
                    and os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT')!='direct') else None


def metadata(conn,user,query):
    _,item,task=discussion.scope(conn,user,query['case_id'],query['task_id'])
    selected=rows(conn,'''SELECT c.id,c.parent_id IS NOT NULL AS is_reply,
        CASE WHEN c.parent_id<>c.id AND EXISTS(SELECT 1 FROM work_comment p
          WHERE p.id=c.parent_id AND p.case_id=c.case_id AND p.task_id IS c.task_id) THEN c.parent_id END AS parent_id,
        (SELECT MAX(r.revision) FROM work_comment_revision r WHERE r.comment_id=c.id) AS revision
        FROM work_comment c WHERE c.id=? AND c.case_id=? AND c.task_id IS ?''',
        (query['comment_id'],query['case_id'],query['task_id']))
    if not selected or selected[0]['revision'] is None:raise ValueError(DENIED)
    return item,task,selected[0]


def source(query,identifier):
    return (links.origin()+'/work/'+str(query['case_id'])+'/discussion?focus='+str(identifier)
            +('&task_id='+str(query['task_id']) if query['task_id'] is not None else '')+'#message-'+str(identifier))


def command(query,identifier,kind='/discussion_thread'):
    if kind=='/discussion_browse':return browse_command(query)
    return kind+' '+str(query['case_id'])+' '+(str(query['task_id']) if query['task_id'] is not None else 'work')+' '+str(identifier)


def browse_command(query):
    return '/discussion_browse '+str(query['case_id'])+' '+(str(query['task_id']) if query['task_id'] is not None else 'work')


def browse(conn,query,item,task,reply_mode,edit_context=None):
    found=rows(conn,'''SELECT c.id,r.revision,
        telegram_discussion_part(r.body,1,:size) AS text,telegram_discussion_length(r.body) AS length
        FROM work_comment c JOIN work_comment_revision r ON r.comment_id=c.id
          AND r.revision=(SELECT MAX(v.revision) FROM work_comment_revision v WHERE v.comment_id=c.id)
        WHERE c.case_id=:case_id AND c.task_id IS :task_id AND c.parent_id IS NULL
          AND (:before=0 OR c.id<:before) ORDER BY c.id DESC LIMIT :limit''',
        {**query,'size':REPLY_PREVIEW,'limit':PAGE_SIZE+1})
    text='Discussion comments · current revisions · newest ID first\n'+header(item,task)
    shown=[]
    for comment in found[:PAGE_SIZE]:
        block=('Comment '+str(comment['id'])+' · Revision '+str(comment['revision'])
               +'\nPreview: '+preview(comment['text'],comment['length'],REPLY_PREVIEW)
               +'\n'+source(query,comment['id'])+'\nView thread: '+command(query,comment['id'])
               +'\nRead message: '+command(query,comment['id'],'/discussion_message')
               +reply_shortcut(query,comment['id'],reply_mode)+edit_shortcut(conn,query,comment,edit_context))
        if common.units(text+'\n\n'+block)>3000:break
        text+='\n\n'+block;shown.append(comment)
    if not found:text+='\nNo current top-level comments on this page. Replies are available inside their threads.'
    if shown and len(shown)<len(found):text+='\nOlder comments: '+browse_command(query)+' before:'+str(shown[-1]['id'])
    return text+'\nTop-level comments only; open a thread for replies. No totals or author labels are shown.'


def reply_shortcut(query,identifier,mode):
    if not mode:return ''
    url=links.origin()+'/account/telegram/reply/'+mode+'?case_id='+str(query['case_id'])
    if query['task_id'] is not None:url+='&task_id='+str(query['task_id'])
    return '\nReply form: '+url+'&parent_id='+str(identifier)


def edit_shortcut(conn,query,selected,context):
    if not context:return ''
    user_id,mode=context
    # Check ownership only with the separate edit grant; never project an author ID.
    own=conn.execute('''SELECT 1 FROM work_comment c WHERE c.id=? AND c.case_id=? AND c.task_id IS ?
        AND c.author_id=? AND (SELECT MAX(r.revision) FROM work_comment_revision r WHERE r.comment_id=c.id)=?''',
        (selected['id'],query['case_id'],query['task_id'],user_id,selected['revision'])).fetchone()
    if not own:return ''
    url=links.origin()+'/account/telegram/comment-edit/'+mode+'?case_id='+str(query['case_id'])
    if query['task_id'] is not None:url+='&task_id='+str(query['task_id'])
    return '\nEdit my message form: '+url+'&comment_id='+str(selected['id'])+'&revision='+str(selected['revision'])


def header(item,task):
    return ('Work '+str(item['id'])+' · '+common.clip(item['title'],80)
            +('\nTask '+str(task['id'])+' · '+common.clip(task['title'],80) if task else '\nWork-level discussion only.'))


def preview(text,length,limit):return common.clip(text,limit)+('…' if length>limit else '')


def text_functions(conn):
    # SQLite TEXT length/substr stop at NUL, which older native plain-text messages can contain.
    # Python codepoint slicing keeps all permitted text addressable without returning full bodies.
    conn.create_function('telegram_discussion_part',3,lambda value,start,size:str(value or '')[start-1:start-1+size],deterministic=True)
    conn.create_function('telegram_discussion_length',1,lambda value:len(str(value or '')),deterministic=True)


def thread(conn,query,item,task,selected,reply_mode=None,edit_context=None):
    root_limit=60 if edit_context else ROOT_PREVIEW
    reply_limit=45 if edit_context else REPLY_PREVIEW
    root=rows(conn,'SELECT telegram_discussion_part(body,1,?) AS text,telegram_discussion_length(body) AS length FROM work_comment_revision WHERE comment_id=? AND revision=?',
              (root_limit,selected['id'],selected['revision']))[0]
    replies=rows(conn,'''SELECT c.id,r.revision,telegram_discussion_part(r.body,1,:size) AS text,telegram_discussion_length(r.body) AS length
        FROM work_comment c JOIN work_comment_revision r ON r.comment_id=c.id
          AND r.revision=(SELECT MAX(v.revision) FROM work_comment_revision v WHERE v.comment_id=c.id)
        WHERE c.case_id=:case_id AND c.task_id IS :task_id AND c.parent_id=:comment_id AND c.id<>:comment_id
          AND (:before=0 OR c.id<:before) ORDER BY c.id DESC LIMIT :limit''',
        {**query,'size':reply_limit,'limit':PAGE_SIZE+1})
    text=('Discussion thread · current revisions\n'+header(item,task)+'\nSelected '+('reply ' if selected['is_reply'] else 'comment ')
          +str(selected['id'])+' · Revision '+str(selected['revision'])+'\nPreview: '+preview(root['text'],root['length'],root_limit)
          +'\n'+source(query,selected['id'])+'\nRead message: '+command(query,selected['id'],'/discussion_message')
          +reply_shortcut(query,selected['id'],reply_mode)+edit_shortcut(conn,query,selected,edit_context))
    if selected['parent_id']:text+='\nParent: '+command(query,selected['parent_id'])
    text+='\n\nDirect replies · newest ID first. Open a reply to view its replies.'
    shown=[]
    for reply in replies[:PAGE_SIZE]:
        block=('Reply '+str(reply['id'])+' · Revision '+str(reply['revision'])+'\nPreview: '+preview(reply['text'],reply['length'],reply_limit)
               +'\n'+source(query,reply['id'])+'\nRead message: '+command(query,reply['id'],'/discussion_message')
               +'\nReplies: '+command(query,reply['id'])+reply_shortcut(query,reply['id'],reply_mode)+edit_shortcut(conn,query,reply,edit_context))
        if common.units(text+'\n\n'+block)>(3400 if edit_context else 3300):break
        text+='\n\n'+block;shown.append(reply)
    if not replies:text+='\nNo direct replies in this current discussion.'
    if shown and len(shown)<len(replies):text+='\nOlder direct replies: '+command(query,selected['id'])+' before:'+str(shown[-1]['id'])
    return text+'\nPreviews are bounded; use Read message for numbered parts. No totals or author labels are shown.'


def message(conn,query,item,task,selected,reply_mode=None,edit_context=None):
    base=command(query,selected['id'],'/discussion_message')
    if query['revision'] and query['revision']!=selected['revision']:
        return 'This message changed. Reopen its current first part:\n'+base
    body=rows(conn,'SELECT telegram_discussion_part(body,?,?) AS text,telegram_discussion_length(body) AS length FROM work_comment_revision WHERE comment_id=? AND revision=?',
              ((query['part']-1)*PART_SIZE+1,PART_SIZE,selected['id'],selected['revision']))[0]
    parts=max(1,(body['length']+PART_SIZE-1)//PART_SIZE)
    if query['part']>parts:return 'That part is unavailable. Reopen the current message:\n'+base
    content=''.join(ch if ch=='\n' or not unicodedata.category(ch).startswith('C') else ' ' for ch in body['text'])
    text=('Discussion message · current revision\n'+header(item,task)+'\nComment '+str(selected['id'])+' · Revision '+str(selected['revision'])
          +' · Part '+str(query['part'])+'/'+str(parts)+'\nText (current part):\n'+content+'\nEnd of message part.\n'+source(query,selected['id']))
    for label,part in (('Previous part',query['part']-1),('Next part',query['part']+1)):
        if 1<=part<=parts:text+='\n'+label+': '+base+' part:'+str(selected['revision'])+':'+str(part)
    return text+'\nThread: '+command(query,selected['id'])+reply_shortcut(query,selected['id'],reply_mode)+edit_shortcut(conn,query,selected,edit_context)


def render(conn,clean,bot,now):
    if not conn.in_transaction:raise RuntimeError('Discussion reading requires the intake transaction')
    found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not found:return None
    link=found[0];context={'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
                         'topic_id':clean['topic_id'],'registration_id':None}
    user=actor(conn,context,bot)
    if not user:return None
    query=clean['discussion_read_query']
    if query=={'error':'usage'}:return USAGE
    try:
        if query['command']=='/discussion_browse':
            _,item,task=discussion.scope(conn,user,query['case_id'],query['task_id'])
        else:item,task,selected=metadata(conn,user,query)
    except ValueError:return DENIED
    text_functions(conn)
    mode='task' if query['task_id'] is not None else 'work'
    reply_mode=mode if links.authorized(conn,user['id'],'tasks.reply' if mode=='task' else 'work.reply') else None
    edit_context=(user['id'],mode) if links.authorized(conn,user['id'],'tasks.comment_edit' if mode=='task' else 'work.comment_edit') else None
    if query['command']=='/discussion_browse':text=browse(conn,query,item,task,reply_mode,edit_context)
    elif query['command']=='/discussion_thread':text=thread(conn,query,item,task,selected,reply_mode,edit_context)
    else:text=message(conn,query,item,task,selected,reply_mode,edit_context)
    if reply_mode and '\nReply form: ' in text:
        text+='\nTo use Reply links, first send /'+reply_mode+'_reply. Enter reply text, preview and confirm privately.'
    if edit_context and '\nEdit my message form: ' in text:
        text+='\nTo edit, first send /'+mode+'_comment_edit privately. Enter replacement text, preview and confirm.'
    return text+'\nText is copied into this private chat. Reading here marks nothing read and changes no records or preferences.'
