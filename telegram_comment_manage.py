"""Exact plain discussion posts; native source visibility and history stay authoritative."""
import json

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_task_review as review
import telegram_work_actions as shared
import work
import work_discussion as discussion
import work_reads

MODES={'work':'work.comment','task':'tasks.comment'}
PATH='/account/telegram/comment/'
FIELDS={'work':('case_id','body'),'task':('case_id','task_id','body')}


class Adapter(review.Adapter):
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS[self.mode]):raise actions.Unavailable('Complete only the supported comment fields.')
        work.writable(conn)
        case_id=proposals.number(raw['case_id'])
        task_id=proposals.number(raw['task_id']) if self.mode=='task' else None
        _,item,_=discussion.scope(conn,user,case_id,task_id)
        task=work_reads.task(conn,user,case_id,task_id) if task_id is not None else None
        clean={'case_id':case_id,'body':proposals.text(raw['body'],'Comment',1000,multiline=True)}
        if task_id is not None:clean['task_id']=task_id
        summary={**clean,'work_title':common.clip(item['title'],120),'work_status':item['status']}
        if task:summary.update(title=common.clip(task['title'],160),status=task['status'])
        if common.units(self.text(summary))>3000:raise actions.Unavailable('This preview is too long. Shorten the comment or use Office Connect.')
        return clean,summary,shared.source_state(conn,item,task)

    def queue_preview(self,conn,user,operation_id,context,now):
        clean=json.loads(rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]['fields_json'])
        conn.execute('UPDATE telegram_operation SET context_json=?,expected_revision=?,target_id=? WHERE operation_id=?',
                     (actions.packed(context),str(clean['case_id']),clean.get('task_id'),operation_id))

    def apply(self,conn,user,clean,operation_id):
        comment_id=discussion.post_in_transaction(conn,user,clean['case_id'],clean['body'],task_id=clean.get('task_id'),mentions=[])
        conn.execute('UPDATE telegram_operation SET comment_id=? WHERE operation_id=?',(comment_id,operation_id))
        return {'state':'committed','result_code':'comment_posted'}

    def text(self,summary):
        target='\nTask '+str(summary['task_id'])+' · '+summary['title']+'\nTask state: '+summary['status'].replace('_',' ') if self.mode=='task' else '\nWork-level discussion (no task selected).'
        return ('Discussion comment preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nWork state: '+summary['work_status'].replace('_',' ')+target+'\nPost as your linked Office Connect account:\n'+summary['body']
                +'\nYour entered text appears in Telegram and the work discussion/history, visible to people with current source access.'
                +'\nNormal follower in-app notices apply. No mentions, reply target or notification preferences are added.'
                +'\nInformal comment only. Work/task progress, ownership, submissions, blockers, dependencies, deadlines and formal approvals stay unchanged.')

    def check_receipt(self,conn,user,operation):
        if not work.enabled(conn):raise actions.Unavailable('Discussion receipt unavailable.')
        if operation['result_code']=='work_deleted':return
        case_id=proposals.number(operation['expected_revision'])
        discussion.scope(conn,user,case_id,operation['target_id'] if self.mode=='task' else None)
        if operation['state']=='committed' and operation['result_code']=='comment_posted':
            current=discussion.message(conn,case_id,operation['target_id'] if self.mode=='task' else None,operation['comment_id'])
            if current['author_id']!=user['id']:raise actions.Unavailable('Discussion receipt unavailable.')

    def receipt_text(self,conn,user,operation):
        self.check_receipt(conn,user,operation)
        if operation['result_code']=='work_deleted':return 'The work for this discussion operation was deleted. Recovery will not recreate it or use a replacement with the same number.'
        if operation['result_code']=='task_deleted':return 'The task for this discussion operation was deleted. Recovery will not recreate it.\n/work_status '+str(operation['expected_revision'])
        if operation['state']!='committed' or not operation['comment_id']:return None
        case_id=proposals.number(operation['expected_revision']);task_id=operation['target_id'] if self.mode=='task' else None
        current=discussion.message(conn,case_id,task_id,operation['comment_id'])
        return ('Recorded outcome: comment posted.\nWork '+str(case_id)+(' · Task '+str(task_id) if task_id is not None else ' · Work-level discussion')
                +'\nComment '+str(current['id'])+' · Current revision '+str(current['revision'])+'\nOperation: '+operation['operation_id']
                +'\n'+links.origin()+'/work/'+str(case_id)+'/discussion?focus='+str(current['id'])+('&task_id='+str(task_id) if task_id is not None else '')+'#message-'+str(current['id'])
                +'\nThe saved text stays in Office Connect. Recovery reports the recorded post and current revision; it never posts again.')


for mode,action in MODES.items():
    prefix=mode+'comment'
    dispatch.register(action,{'prefix':prefix,'start':'/'+mode+'_comment','path':PATH+mode,
                              'confirm':'/'+prefix+'_confirm','receipt':'/'+prefix+'_receipt'},Adapter(mode))
COMMANDS=tuple(command for mode in MODES for command in
               ('/'+mode+'_comment','/'+mode+'comment_preview','/'+mode+'comment_confirm','/'+mode+'comment_receipt'))
