"""Private coordinator-authorized internal task deadlines; official dates stay unchanged."""
from datetime import date
import json
import re

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_work_actions as shared
import work
import work_reads
import work_tasks

ACTION='tasks.deadline'
MODES={'change':ACTION}
PATH='/account/telegram/task-deadline/'
FIELDS=('case_id','task_id','deadline_mode','due_date','reason')


class Adapter:
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS):
            raise actions.Unavailable('Complete only the supported deadline fields.')
        item=shared.require_work(conn,user,proposals.number(raw['case_id']))
        task=work_reads.task(conn,user,item['id'],proposals.number(raw['task_id']))
        if 'milestone' not in work_tasks.actions(conn,user,item,task):
            raise actions.Unavailable('Only the concerned officer or confirmed work lead can change this current task deadline.')
        mode=raw['deadline_mode'];due=raw['due_date']
        if mode not in ('set','clear') or not isinstance(due,str):
            raise actions.Unavailable('Choose whether to set or explicitly clear the internal deadline.')
        if mode=='set':
            if not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',due):
                raise actions.Unavailable('Choose an exact new deadline.')
            date.fromisoformat(due)
        elif due:
            raise actions.Unavailable('Leave the date blank when explicitly clearing the internal deadline.')
        normalized=work_tasks._due(conn,item['id'],due)
        if normalized==task['due_date']:
            raise actions.Unavailable('The task already has that deadline.')
        clean={'case_id':item['id'],'task_id':task['id'],'deadline_mode':mode,'due_date':normalized or '',
               'reason':proposals.text(raw['reason'],'Deadline-change reason',500,multiline=True)}
        summary={**clean,'work_title':common.clip(item['title'],120),'title':common.clip(task['title'],160),
                 'old_due':task['due_date'] or 'not set','status':task['status']}
        if common.units(self.text(summary))>3000:
            raise actions.Unavailable('This preview is too long. Shorten the reason or use Office Connect.')
        return clean,summary,{**shared.source_state(conn,item,task),'task_revision':task['revision']}

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:
            raise actions.Unavailable('The task, work or linked official deadline changed. Prepare a fresh preview.')

    def apply(self,conn,user,clean,operation_id):
        task=work_reads.task(conn,user,clean['case_id'],clean['task_id'])
        work_tasks.mutate_in_transaction(conn,user,clean['case_id'],clean['task_id'],task['revision'],'milestone',
                                        {'due_date':clean['due_date'],'reason':clean['reason']})
        return {'state':'committed','result_code':'task_deadline_cleared' if clean['deadline_mode']=='clear' else 'task_deadline_changed'}

    def queue_preview(self,conn,user,operation_id,context,now):
        preview=rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]
        clean=json.loads(preview['fields_json'])
        # Generic target is the task; receipt routing retains the work ID separately.
        conn.execute('UPDATE telegram_operation SET context_json=?,target_id=?,expected_revision=? WHERE operation_id=?',
                     (actions.packed(context),clean['task_id'],str(clean['case_id']),operation_id))

    def text(self,summary):
        return ('Task deadline preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nTask '+str(summary['task_id'])+' · '+summary['title']+'\nCurrent status: '+summary['status'].replace('_',' ')
                +'\nCurrent internal deadline: '+summary['old_due']+'\nNew internal deadline: '+(summary['due_date'] or 'explicitly removed')
                +' · Asia/Manila\nReason:\n'+summary['reason']
                +'\nOnly the internal task deadline changes. Owner, progress, submission and official document deadlines stay unchanged.'
                +'\nNormal work history and reminder rules still apply.')

    def check_receipt(self,conn,user,operation):
        if not work.enabled(conn):raise actions.Unavailable('Deadline receipt unavailable.')
        case_id=proposals.number(operation['expected_revision'])
        work.get(conn,user,case_id)
        if operation['target_id']:work_reads.task(conn,user,case_id,operation['target_id'])

    def receipt_text(self,conn,user,operation):
        case_id=proposals.number(operation['expected_revision'])
        if operation['result_code']=='task_deleted':
            return 'The task for this operation was deleted. Recovery will not recreate it.\n/work_status '+str(case_id)
        if operation['state']!='committed' or not operation['target_id']:return None
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        outcome='internal task deadline cleared' if operation['result_code']=='task_deadline_cleared' else 'internal task deadline changed'
        return ('Recorded outcome: '+outcome+'.\nTask '+str(task['id'])+' · Work '+str(case_id)
                +'\nCurrent internal deadline: '+(task['due_date'] or 'not set')+' · Asia/Manila'
                +'\nCurrent status: '+task['status'].replace('_',' ')+'\nOperation: '+operation['operation_id']
                +'\n/work_status '+str(case_id)+'\n'+links.origin()+'/work/'+str(case_id)
                +'\nRecovery reports the recorded outcome and current state; it never repeats the change.')


dispatch.register(ACTION,{'prefix':'deadline','start':'/task_deadline','path':PATH+'change',
                          'confirm':'/deadline_confirm','receipt':'/deadline_receipt'},Adapter())
COMMANDS=('/task_deadline','/deadline_preview','/deadline_confirm','/deadline_receipt')
