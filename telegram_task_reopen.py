"""Private reopening of accepted contributions; work and official documents stay separate."""
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_task_review as review
import work_reads
import work_tasks

ACTION='tasks.reopen'
MODES={'reopen':ACTION}
PATH='/account/telegram/task-reopening/'
FIELDS=review.FIELDS


class Adapter(review.Adapter):
    authority_message='Only the concerned case officer or confirmed work lead can reopen a Done task in open work. Task ownership alone is insufficient.'

    def __init__(self):super().__init__('reopen')

    def prepare(self,conn,user,raw):
        clean,summary,expected=super().prepare(conn,user,raw)
        # Reopening keeps ownership; the existing owner must still pass native contributor checks.
        work_tasks._owner(conn,clean['case_id'],proposals.number(summary['owner_id']))
        return clean,summary,expected

    def apply(self,conn,user,clean,operation_id):
        task=work_reads.task(conn,user,clean['case_id'],clean['task_id'])
        work_tasks.mutate_in_transaction(conn,user,clean['case_id'],clean['task_id'],task['revision'],'reopen',
                                        {'reason':clean['reason']})
        return {'state':'committed','result_code':'task_reopened'}

    def text(self,summary):
        return ('Task reopening preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nTask '+str(summary['task_id'])+' · '+summary['title']
                +'\nOwner account (unchanged): '+str(summary['owner_id'])
                +'\nCurrent status: done\nNew status: in progress\nReason:\n'+summary['reason']
                +'\nReturns this accepted task to In progress for its current owner. Existing submission, history and deadlines are preserved.'
                +'\nReview the submission in Office Connect; submission contents stay there. Existing blockers remain and normal resubmission/review is required.'
                +'\nThis does not reopen a completed work case, reopen/approve an official document or grant access.'
                +'\nNormal task history and reminder rules apply.')

    def receipt_text(self,conn,user,operation):
        if operation['result_code']=='task_deleted':return super().receipt_text(conn,user,operation)
        if operation['state']!='committed' or not operation['target_id']:return None
        case_id=proposals.number(operation['expected_revision'])
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        return ('Recorded outcome: task reopened.\nTask '+str(task['id'])+' · Work '+str(case_id)
                +'\nCurrent owner account: '+str(task['owner_id'] or 'not assigned')
                +'\nCurrent status: '+task['status'].replace('_',' ')+'\nOperation: '+operation['operation_id']
                +'\n/work_status '+str(case_id)+'\n'+links.origin()+'/work/'+str(case_id)
                +'\nRecovery reports the recorded outcome and current state; it never repeats the reopening.')


dispatch.register(ACTION,{'prefix':'taskreopen','start':'/task_reopen','path':PATH+'reopen',
                          'confirm':'/taskreopen_confirm','receipt':'/taskreopen_receipt'},Adapter())
COMMANDS=('/task_reopen','/taskreopen_preview','/taskreopen_confirm','/taskreopen_receipt')
