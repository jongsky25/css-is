"""Private participant-authorized blocker recording and clearing; source rules remain native."""
from datetime import date
import re

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_assign as assignment
import telegram_task_create as proposals
import telegram_task_review as review
import telegram_work_actions as shared
import work
import work_blockers as blockers
import work_reads
import work_tasks

MODES={'block':'tasks.block','unblock':'tasks.unblock'}
PATH='/account/telegram/task-blocker/'
FIELDS={'block':('case_id','task_id','reason','followup_owner_id','followup_date'),
        'unblock':('case_id','task_id','reason')}
def choices(conn,user,mode):
    return assignment.choices(conn,user,mode) if mode=='block' else {}


class Adapter(review.Adapter):
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS[self.mode]):raise actions.Unavailable('Complete only the supported blocker fields.')
        item=shared.require_work(conn,user,proposals.number(raw['case_id']))
        task=work_reads.task(conn,user,item['id'],proposals.number(raw['task_id']))
        can_block,coordinator=blockers.authority(conn,user,item,task)
        if not can_block:raise actions.Unavailable('Current task-owner, follow-up-owner, lead or concerned-officer authority is required for this active task.')
        clean={'case_id':item['id'],'task_id':task['id'],'reason':proposals.text(raw['reason'],'Blocker or resolution reason',500,multiline=True)}
        selected=None
        if self.mode=='block':
            if task['blocker_reason']:raise actions.Unavailable('A blocker is already recorded. Amend it in Office Connect or prepare a separate clearing confirmation.')
            owner_id=work_tasks._owner(conn,item['id'],proposals.number(raw['followup_owner_id']))
            account=work._account(conn,owner_id)
            work.get(conn,account,item['id'])
            if not coordinator and owner_id not in (user['id'],task['blocker_owner_id']):
                raise actions.Unavailable('Ask the lead or an officer to assign another follow-up owner.')
            due=raw['followup_date']
            if not isinstance(due,str) or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',due):raise actions.Unavailable('Choose an exact follow-up date.')
            due=date.fromisoformat(due).isoformat()
            name=rows(conn,'''SELECT COALESCE(NULLIF(r.name,''),u.username) AS name FROM admin_user u
                LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.id=?''',(owner_id,))[0]['name']
            selected={k:account[k] for k in ('id','username','role','active','rp_id')};selected['name']=name
            clean.update(followup_owner_id=owner_id,followup_date=due)
        elif not task['blocker_reason']:raise actions.Unavailable('There is no recorded blocker to clear.')
        summary={**clean,'work_title':common.clip(item['title'],120),'title':common.clip(task['title'],160),
                 'status':task['status'],'followup_name':common.clip(selected['name'],100) if selected else ''}
        if common.units(self.text(summary))>3000:raise actions.Unavailable('This preview is too long. Shorten the reason or use Office Connect.')
        return clean,summary,{**shared.source_state(conn,item,task),'task_revision':task['revision'],'followup':selected}

    def apply(self,conn,user,clean,operation_id):
        task=work_reads.task(conn,user,clean['case_id'],clean['task_id'])
        blockers.mutate_in_transaction(conn,user,clean['case_id'],clean['task_id'],task['revision'],self.mode,
                                       {k:v for k,v in clean.items() if k not in ('case_id','task_id')})
        return {'state':'committed','result_code':'blocker_recorded' if self.mode=='block' else 'blocker_cleared'}

    def text(self,summary):
        text=('Task blocker preview: '+('record' if self.mode=='block' else 'clear')+'\nWork '+str(summary['case_id'])+' · '+summary['work_title']
              +'\nTask '+str(summary['task_id'])+' · '+summary['title']+'\nTask state (unchanged): '+summary['status'].replace('_',' '))
        if self.mode=='block':
            text+='\nRecord a new blocker.\nFollow-up: '+summary['followup_name']+' (account '+str(summary['followup_owner_id'])+')\nFollow-up due: '+summary['followup_date']+' · Asia/Manila'
        else:text+='\nClear the current recorded blocker and its follow-up owner/date. Existing blocker details stay in Office Connect.'
        return (text+'\n'+('Blocker reason' if self.mode=='block' else 'Resolution reason')+':\n'+summary['reason']
                +'\nYour entered reason is shown in Telegram and normal source history.'
                +'\nTask owner, state, submission, task deadline and dependencies stay unchanged. Clearing this blocker does not resolve prerequisites or changed decisions.'
                +'\nNative submission/acceptance rules still apply; no access or official document approval is granted.')

    def receipt_text(self,conn,user,operation):
        if operation['result_code']=='task_deleted':return super().receipt_text(conn,user,operation)
        if operation['state']!='committed' or not operation['target_id']:return None
        case_id=proposals.number(operation['expected_revision'])
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        return ('Recorded outcome: '+('blocker recorded' if operation['result_code']=='blocker_recorded' else 'blocker cleared')+'.'
                +'\nTask '+str(task['id'])+' · Work '+str(case_id)+'\nCurrent recorded blocker: '+('yes' if task['blocker_reason'] else 'no')
                +'\nCurrent task state: '+task['status'].replace('_',' ')+'\nOperation: '+operation['operation_id']
                +'\n'+links.origin()+'/work/'+str(case_id)+'#task-'+str(task['id'])
                +'\nRecovery reports recorded outcome/current state; it never repeats the change or displays the stored blocker reason.')


for mode,action in MODES.items():
    prefix='task'+mode
    dispatch.register(action,{'prefix':prefix,'start':'/task_'+mode,'path':PATH+mode,
                              'confirm':'/'+prefix+'_confirm','receipt':'/'+prefix+'_receipt'},Adapter(mode))
COMMANDS=tuple(command for mode in MODES for command in
               ('/task_'+mode,'/task'+mode+'_preview','/task'+mode+'_confirm','/task'+mode+'_receipt'))
