"""Private officer cancellation with explicit contribution and dependency effects."""
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_task_review as review
import work_reads
import work_tasks

ACTION='tasks.cancel'
MODES={'cancel':ACTION}
PATH='/account/telegram/task-cancellation/'
FIELDS=review.FIELDS


class Adapter(review.Adapter):
    authority_message='Only the concerned contributing-unit officer can cancel an unfinished task. Work-lead or task-owner status alone is insufficient.'

    def __init__(self):super().__init__('cancel')

    def apply(self,conn,user,clean,operation_id):
        task=work_reads.task(conn,user,clean['case_id'],clean['task_id'])
        work_tasks.mutate_in_transaction(conn,user,clean['case_id'],clean['task_id'],task['revision'],'cancel',
                                        {'reason':clean['reason']})
        return {'state':'committed','result_code':'task_cancelled'}

    def text(self,summary):
        return ('Task cancellation preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nTask '+str(summary['task_id'])+' · '+summary['title']+'\nContributing unit: '+str(summary['unit_id'])
                +'\nContribution: '+('required' if summary['mandatory'] else 'optional')
                +'\nOwner account (retained): '+str(summary['owner_id'] or 'not assigned')
                +'\nCurrent status: '+summary['status'].replace('_',' ')+'\nNew status: cancelled\nReason:\n'+summary['reason']
                +'\nCancellation removes this task from outstanding-contribution checks. It does not accept its output; dependent tasks requiring its acceptance remain blocked.'
                +'\nOwner fields, previous submission, deadline and history are retained. Submission contents stay in Office Connect.'
                +'\nNormal membership rules apply; an owner may lose work access without another source right.'
                +'\nThis does not complete/cancel the work or cancel/approve an official document. Cancelled tasks cannot use task reopening.'
                +'\nNormal task history and reminder rules apply.')

    def receipt_text(self,conn,user,operation):
        if operation['result_code']=='task_deleted':return super().receipt_text(conn,user,operation)
        if operation['state']!='committed' or not operation['target_id']:return None
        case_id=proposals.number(operation['expected_revision'])
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        return ('Recorded outcome: task cancelled.\nTask '+str(task['id'])+' · Work '+str(case_id)
                +'\nCurrent status: '+task['status'].replace('_',' ')+'\nOperation: '+operation['operation_id']
                +'\n/work_status '+str(case_id)+'\n'+links.origin()+'/work/'+str(case_id)
                +'\nRecovery reports the recorded outcome and current state; it never repeats cancellation.')


dispatch.register(ACTION,{'prefix':'taskcancel','start':'/task_cancel','path':PATH+'cancel',
                          'confirm':'/taskcancel_confirm','receipt':'/taskcancel_receipt'},Adapter())
COMMANDS=('/task_cancel','/taskcancel_preview','/taskcancel_confirm','/taskcancel_receipt')
