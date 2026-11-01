"""Private accept/return actions using current native task review authority."""
import json

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

MODES={'accept':'tasks.accept','return':'tasks.return'}
PATH='/account/telegram/task-review/'
FIELDS=('case_id','task_id','reason')


class Adapter:
    authority_message='This submitted task review requires current officer or confirmed work-lead authority and source blockers must permit the action.'

    def __init__(self,mode):self.mode=mode

    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS):
            raise actions.Unavailable('Complete only the supported task review fields.')
        item=shared.require_work(conn,user,proposals.number(raw['case_id']))
        task=work_reads.task(conn,user,item['id'],proposals.number(raw['task_id']))
        if self.mode not in work_tasks.actions(conn,user,item,task):
            raise actions.Unavailable(self.authority_message)
        clean={'case_id':item['id'],'task_id':task['id'],
               'reason':proposals.text(raw['reason'],'Review reason',500,multiline=True)}
        summary={**clean,'work_title':common.clip(item['title'],120),'title':common.clip(task['title'],160),
                 'status':task['status'],'owner_id':task['owner_id'],'next_status':'done' if self.mode=='accept' else 'in_progress'}
        if common.units(self.text(summary))>3000:
            raise actions.Unavailable('This preview is too long. Shorten the reason or use Office Connect.')
        return clean,summary,{**shared.source_state(conn,item,task),'task_revision':task['revision']}

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:
            raise actions.Unavailable('The task, submission, work or linked document changed. Prepare a fresh preview.')

    def apply(self,conn,user,clean,operation_id):
        task=work_reads.task(conn,user,clean['case_id'],clean['task_id'])
        work_tasks.mutate_in_transaction(conn,user,clean['case_id'],clean['task_id'],task['revision'],self.mode,
                                        {'reason':clean['reason']})
        return {'state':'committed','result_code':'task_accepted' if self.mode=='accept' else 'task_returned'}

    def queue_preview(self,conn,user,operation_id,context,now):
        preview=rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]
        clean=json.loads(preview['fields_json'])
        conn.execute('UPDATE telegram_operation SET context_json=?,target_id=?,expected_revision=? WHERE operation_id=?',
                     (actions.packed(context),clean['task_id'],str(clean['case_id']),operation_id))

    def text(self,summary):
        label='Accept submitted task' if self.mode=='accept' else 'Return submitted task for changes'
        return ('Task review preview: '+label+'\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nTask '+str(summary['task_id'])+' · '+summary['title']
                +'\nCurrent status: '+summary['status'].replace('_',' ')+'\nNew status: '+summary['next_status'].replace('_',' ')
                +'\nReason:\n'+summary['reason']
                +'\nReview the current submission in Office Connect before confirming. Submission contents stay in Office Connect.'
                +'\nOwner, submission and deadlines stay unchanged. This does not complete the work or approve an official document.'
                +'\nNormal task history and reminder rules apply.')

    def check_receipt(self,conn,user,operation):
        if not work.enabled(conn):raise actions.Unavailable('Task review receipt unavailable.')
        case_id=proposals.number(operation['expected_revision'])
        work.get(conn,user,case_id)
        if operation['target_id']:work_reads.task(conn,user,case_id,operation['target_id'])

    def receipt_text(self,conn,user,operation):
        case_id=proposals.number(operation['expected_revision'])
        if operation['result_code']=='task_deleted':
            return 'The task for this operation was deleted. Recovery will not recreate it.\n/work_status '+str(case_id)
        if operation['state']!='committed' or not operation['target_id']:return None
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        outcome='task accepted' if operation['result_code']=='task_accepted' else 'task returned for changes'
        return ('Recorded outcome: '+outcome+'.\nTask '+str(task['id'])+' · Work '+str(case_id)
                +'\nCurrent status: '+task['status'].replace('_',' ')+'\nOperation: '+operation['operation_id']
                +'\n/work_status '+str(case_id)+'\n'+links.origin()+'/work/'+str(case_id)
                +'\nRecovery reports the recorded outcome and current state; it never repeats the review.')


for mode,action in MODES.items():
    prefix='task'+mode
    dispatch.register(action,{'prefix':prefix,'start':'/task_'+mode,'path':PATH+mode,
                              'confirm':'/'+prefix+'_confirm','receipt':'/'+prefix+'_receipt'},Adapter(mode))
COMMANDS=tuple(command for mode in MODES for command in
               ('/task_'+mode,'/task'+mode+'_preview','/task'+mode+'_confirm','/task'+mode+'_receipt'))
