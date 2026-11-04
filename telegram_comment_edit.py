"""Author-only exact comment edits; native revision history and mention rules remain authoritative."""
import hashlib
import json

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_comment_manage as comments
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_work_actions as shared
import work
import work_discussion as discussion
import work_reads
import work_updates

MODES={'work':'work.comment_edit','task':'tasks.comment_edit'}
PATH='/account/telegram/comment-edit/'
FIELDS={'work':('case_id','comment_id','revision','body'),
        'task':('case_id','task_id','comment_id','revision','body')}


class Adapter(comments.Adapter):
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS[self.mode]):raise actions.Unavailable('Complete only the supported comment edit fields.')
        work.writable(conn)
        case_id=proposals.number(raw['case_id']);task_id=proposals.number(raw['task_id']) if self.mode=='task' else None
        _,item,_=discussion.scope(conn,user,case_id,task_id)
        task=work_reads.task(conn,user,case_id,task_id) if task_id is not None else None
        current=discussion.message(conn,case_id,task_id,proposals.number(raw['comment_id']))
        if current['author_id']!=user['id']:raise actions.Unavailable('Only the original author can edit this comment.')
        revision=proposals.number(raw['revision'])
        if current['revision']!=revision:raise actions.Unavailable('This comment was edited elsewhere. Review its current revision and prepare a fresh preview.')
        body=proposals.text(raw['body'],'Replacement comment',1000,multiline=True)
        if body==current['body']:raise actions.Unavailable('There is no text change to save.')
        mentions=work_updates.mentions(conn,current['id'],revision)
        work_updates.validate_mentions(conn,case_id,[m['user_id'] for m in mentions])
        clean={'case_id':case_id,'comment_id':current['id'],'revision':revision,'body':body}
        if task_id is not None:clean['task_id']=task_id
        summary={**clean,'work_title':common.clip(item['title'],120),'work_status':item['status'],
                 'parent_id':current['parent_id'],'mention_count':len(mentions)}
        if task:summary.update(title=common.clip(task['title'],160),status=task['status'])
        if common.units(self.text(summary))>3000:raise actions.Unavailable('This preview is too long. Shorten the replacement text or use Office Connect.')
        digest=hashlib.sha256(json.dumps([current,mentions],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return clean,summary,{**shared.source_state(conn,item,task),'comment':digest}

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:raise actions.Unavailable('The comment, existing mentions, work, selected task or linked records changed. Prepare a fresh edit preview.')

    def queue_preview(self,conn,user,operation_id,context,now):
        super().queue_preview(conn,user,operation_id,context,now)
        clean=json.loads(rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]['fields_json'])
        conn.execute('UPDATE telegram_operation SET comment_id=? WHERE operation_id=?',(clean['comment_id'],operation_id))

    def apply(self,conn,user,clean,operation_id):
        discussion.edit_in_transaction(conn,user,clean['case_id'],clean.get('task_id'),clean['comment_id'],clean['revision'],clean['body'],mentions=None)
        current=discussion.message(conn,clean['case_id'],clean.get('task_id'),clean['comment_id'])
        if current['revision']!=clean['revision']+1:raise actions.Unavailable('No new comment revision was recorded.')
        conn.execute('UPDATE telegram_operation SET comment_revision=? WHERE operation_id=?',(current['revision'],operation_id))
        return {'state':'committed','result_code':'comment_edited'}

    def text(self,summary):
        target='\nTask '+str(summary['task_id'])+' · '+summary['title']+'\nTask state: '+summary['status'].replace('_',' ') if self.mode=='task' else '\nWork-level discussion (no task selected).'
        url=(links.origin()+'/work/'+str(summary['case_id'])+'/discussion?focus='+str(summary['comment_id'])
             +('&task_id='+str(summary['task_id']) if self.mode=='task' else '')+'#message-'+str(summary['comment_id']))
        return ('Discussion edit preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nWork state: '+summary['work_status'].replace('_',' ')+target
                +'\nEdit your comment '+str(summary['comment_id'])+' · Revision '+str(summary['revision'])+' → '+str(summary['revision']+1)
                +('\nReply parent (unchanged): comment '+str(summary['parent_id']) if summary['parent_id'] else '\nThis is a top-level comment; thread stays unchanged.')
                +'\nReview existing text/history in Office Connect:\n'+url+'\nSave this complete replacement text:\n'+summary['body']
                +'\nYour entered replacement appears in Telegram and discussion history for people with current source access. Previous revisions are retained.'
                +'\nExisting structured mentions retained: '+str(summary['mention_count'])+'. Their current access is rechecked; native edit notice/read rules apply.'
                +'\nNo new comment, parent, mentions or notification preferences. Work/task progress, submissions, blockers, dependencies, deadlines and approvals stay unchanged.')

    def check_receipt(self,conn,user,operation):
        if not work.enabled(conn):raise actions.Unavailable('Comment edit receipt unavailable.')
        if operation['result_code']=='work_deleted':return
        case_id=proposals.number(operation['expected_revision']);task_id=operation['target_id'] if self.mode=='task' else None
        discussion.scope(conn,user,case_id,task_id)
        if operation['comment_id']:
            current=discussion.message(conn,case_id,task_id,operation['comment_id'])
            if current['author_id']!=user['id']:raise actions.Unavailable('Comment edit receipt unavailable.')

    def receipt_text(self,conn,user,operation):
        self.check_receipt(conn,user,operation)
        if operation['result_code'] in ('work_deleted','task_deleted'):return super().receipt_text(conn,user,operation)
        if operation['state']!='committed' or not operation['comment_id']:return None
        case_id=proposals.number(operation['expected_revision']);task_id=operation['target_id'] if self.mode=='task' else None
        current=discussion.message(conn,case_id,task_id,operation['comment_id'])
        return ('Recorded outcome: comment edited.\nWork '+str(case_id)+(' · Task '+str(task_id) if task_id is not None else ' · Work-level discussion')
                +'\nComment '+str(current['id'])+'\nRecorded edit revision: '+str(operation['comment_revision'])+'\nCurrent comment revision: '+str(current['revision'])
                +'\nOperation: '+operation['operation_id']+'\n'+links.origin()+'/work/'+str(case_id)+'/discussion?focus='+str(current['id'])
                +('&task_id='+str(task_id) if task_id is not None else '')+'#message-'+str(current['id'])
                +'\nSaved text/history stay in Office Connect. Recovery never repeats the edit or overwrites a later revision.')


for mode,action in MODES.items():
    prefix=mode+'edit'
    dispatch.register(action,{'prefix':prefix,'start':'/'+mode+'_comment_edit','path':PATH+mode,
                              'confirm':'/'+prefix+'_confirm','receipt':'/'+prefix+'_receipt'},Adapter(mode))
COMMANDS=tuple(command for mode in MODES for command in
               ('/'+mode+'_comment_edit','/'+mode+'edit_preview','/'+mode+'edit_confirm','/'+mode+'edit_receipt'))
