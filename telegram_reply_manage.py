"""Exact replies to existing same-thread comments; parent text remains in Office Connect."""
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

MODES={'work':'work.reply','task':'tasks.reply'}
PATH='/account/telegram/reply/'
FIELDS={'work':('case_id','parent_id','body'),'task':('case_id','task_id','parent_id','body')}


class Adapter(comments.Adapter):
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS[self.mode]):raise actions.Unavailable('Complete only the supported reply fields.')
        work.writable(conn)
        case_id=proposals.number(raw['case_id'])
        task_id=proposals.number(raw['task_id']) if self.mode=='task' else None
        _,item,_=discussion.scope(conn,user,case_id,task_id)
        task=work_reads.task(conn,user,case_id,task_id) if task_id is not None else None
        parent=discussion.message(conn,case_id,task_id,proposals.number(raw['parent_id']))
        clean={'case_id':case_id,'parent_id':parent['id'],'body':proposals.text(raw['body'],'Reply',1000,multiline=True)}
        if task_id is not None:clean['task_id']=task_id
        summary={**clean,'work_title':common.clip(item['title'],120),'work_status':item['status'],'parent_revision':parent['revision']}
        if task:summary.update(title=common.clip(task['title'],160),status=task['status'])
        if common.units(self.text(summary))>3000:raise actions.Unavailable('This preview is too long. Shorten the reply or use Office Connect.')
        digest=hashlib.sha256(json.dumps(parent,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return clean,summary,{**shared.source_state(conn,item,task),'parent':digest}

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:raise actions.Unavailable('The parent comment, work, selected task or linked records changed. Prepare a fresh reply preview.')

    def apply(self,conn,user,clean,operation_id):
        comment_id=discussion.post_in_transaction(conn,user,clean['case_id'],clean['body'],task_id=clean.get('task_id'),parent_id=clean['parent_id'],mentions=[])
        conn.execute('UPDATE telegram_operation SET comment_id=? WHERE operation_id=?',(comment_id,operation_id))
        return {'state':'committed','result_code':'comment_posted'}

    def text(self,summary):
        target='\nTask '+str(summary['task_id'])+' · '+summary['title']+'\nTask state: '+summary['status'].replace('_',' ') if self.mode=='task' else '\nWork-level discussion (no task selected).'
        parent_url=(links.origin()+'/work/'+str(summary['case_id'])+'/discussion?focus='+str(summary['parent_id'])
                    +('&task_id='+str(summary['task_id']) if self.mode=='task' else '')+'#message-'+str(summary['parent_id']))
        return ('Discussion reply preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nWork state: '+summary['work_status'].replace('_',' ')+target
                +'\nReply to comment '+str(summary['parent_id'])+' · Revision '+str(summary['parent_revision'])
                +'\nReview the parent text in Office Connect:\n'+parent_url+'\nPost this reply as your linked account:\n'+summary['body']
                +'\nYour entered reply appears in Telegram and normal discussion history for people with current source access.'
                +'\nNormal follower and eligible parent-author notices apply. No mentions or notification preferences are added.'
                +'\nInformal reply only. Work/task progress, submissions, blockers, dependencies, deadlines and formal approvals stay unchanged.')

    def check_receipt(self,conn,user,operation):
        super().check_receipt(conn,user,operation)
        if operation['state']=='committed' and operation['result_code']=='comment_posted':
            current=discussion.message(conn,proposals.number(operation['expected_revision']),operation['target_id'] if self.mode=='task' else None,operation['comment_id'])
            if current['parent_id'] is None:raise actions.Unavailable('Reply receipt unavailable.')

    def receipt_text(self,conn,user,operation):
        text=super().receipt_text(conn,user,operation)
        if text and operation['state']=='committed' and operation['result_code']=='comment_posted':
            current=discussion.message(conn,proposals.number(operation['expected_revision']),operation['target_id'] if self.mode=='task' else None,operation['comment_id'])
            text=text.replace('Recorded outcome: comment posted.','Recorded outcome: reply posted.\nReply to comment '+str(current['parent_id'])+'.',1)
        return text


for mode,action in MODES.items():
    prefix=mode+'reply'
    dispatch.register(action,{'prefix':prefix,'start':'/'+mode+'_reply','path':PATH+mode,
                              'confirm':'/'+prefix+'_confirm','receipt':'/'+prefix+'_receipt'},Adapter(mode))
COMMANDS=tuple(command for mode in MODES for command in
               ('/'+mode+'_reply','/'+mode+'reply_preview','/'+mode+'reply_confirm','/'+mode+'reply_receipt'))
