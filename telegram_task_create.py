"""Guided task proposals; native officer assignment and source rules remain authoritative."""
from datetime import date
import hashlib
import json
import re
import unicodedata

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import work
import work_compat
import work_reads
import work_tasks

ACTION='tasks.create'
MODES={'create':ACTION}
PATH='/account/telegram/task/'
FIELDS=('case_id','title','expected_output','unit_id','proposed_owner_id','due_date')


def number(value,optional=False):
    if optional and value in ('',None):return None
    if type(value) not in (int,str) or not re.fullmatch('[1-9][0-9]{0,17}',str(value)):
        raise actions.Unavailable('Choose a valid work item, unit or active account.')
    return int(value)


def text(value,label,limit,multiline=False):
    if isinstance(value,str) and multiline:value=value.replace('\r\n','\n').replace('\r','\n')
    if not isinstance(value,str) or any(unicodedata.category(c).startswith('C') and not (multiline and c=='\n') for c in value):
        raise actions.Unavailable('Use plain text without control characters.')
    return work._text(value,label,limit)


def choices(conn,user,mode):
    return {'people':rows(conn,'''SELECT u.id,COALESCE(NULLIF(r.name,''),u.username) AS name
        FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.active=1 ORDER BY name,u.id'''),
            'units':rows(conn,'SELECT id,name FROM org_unit ORDER BY path,id')}


class Adapter:
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS):raise actions.Unavailable('Complete only the supported task proposal fields.')
        work.writable(conn)
        item=work.get(conn,user,number(raw['case_id']))
        work_compat.require_open(conn,item['id'])
        # Native creation invalidates active consolidation packets, including
        # downstream formal approvals. Keep that larger amendment in the source UI.
        if conn.execute('''SELECT 1 FROM work_review_packet p JOIN document d ON d.id=p.document_id
            WHERE p.case_id=? AND d.status NOT IN ('closed','cancelled','released','awaiting_acknowledgment')
            AND NOT EXISTS(SELECT 1 FROM work_review_packet newer WHERE newer.document_id=p.document_id AND newer.id>p.id)
            AND NOT EXISTS(SELECT 1 FROM work_review_invalidation i WHERE i.packet_id=p.id) LIMIT 1''',(item['id'],)).fetchone():
            raise actions.Unavailable('Amend work under active consolidation review in Office Connect so dependent approvals can be reviewed there.')
        unit_id=number(raw['unit_id'],optional=True) or item['unit_id']
        unit=rows(conn,'SELECT id,name,path FROM org_unit WHERE id=?',(unit_id,))
        if not unit:raise actions.Unavailable('Choose an existing contributing unit.')
        owner_id=number(raw['proposed_owner_id'],optional=True)
        owner=None
        if owner_id:
            account=work._account(conn,owner_id)
            name=rows(conn,'''SELECT COALESCE(NULLIF(r.name,''),u.username) AS name
                FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.id=?''',(owner_id,))[0]['name']
            owner={k:account[k] for k in ('id','username','role','active','rp_id')}
            owner['name']=name
        due=raw['due_date']
        if not isinstance(due,str) or (due and not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',due)):
            raise actions.Unavailable('Choose an exact deadline or leave it blank.')
        if due:date.fromisoformat(due)
        # Same linked official-deadline rule used by native creation.
        due=work_tasks._due(conn,item['id'],due)
        clean={'case_id':item['id'],'title':text(raw['title'],'Task title',160),
               'expected_output':text(raw['expected_output'],'Expected output',1000,multiline=True),
               'unit_id':unit_id,'proposed_owner_id':owner_id,'due_date':due or ''}
        documents=[]
        for link in rows(conn,'SELECT * FROM work_document WHERE case_id=? ORDER BY document_id',(item['id'],)):
            doc=work.resolved_document(conn,link['document_id'])
            documents.append([link,{k:doc[k] for k in ('id','canonical_id','revision','due_date','status')} if doc else None])
        expected={'source':hashlib.sha256(actions.packed([item,documents]).encode()).hexdigest(),
                  'event_id':conn.execute('SELECT COALESCE(MAX(id),0) FROM work_event WHERE case_id=?',(item['id'],)).fetchone()[0],
                  'unit':unit[0],'owner':owner}
        summary={**clean,'work_title':common.clip(item['title'],120),'unit_name':common.clip(unit[0]['name'],120),
                 'owner_name':common.clip(owner['name'],120) if owner else 'None proposed'}
        if common.units(self.text(summary))>3000:
            raise actions.Unavailable('This preview is too long. Shorten the task title or expected output.')
        return clean,summary,expected

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:raise actions.Unavailable('The work, deadline, unit or proposed account changed. Prepare a new preview.')

    def apply(self,conn,user,clean,operation_id):
        task=work_tasks.create_in_transaction(conn,user,clean['case_id'],{k:v for k,v in clean.items() if k!='case_id'})
        conn.execute('UPDATE telegram_operation SET target_id=? WHERE operation_id=?',(task['id'],operation_id))
        return {'state':'committed','result_code':'task_proposed'}

    def queue_preview(self,conn,user,operation_id,context,now):
        preview=rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]
        clean=json.loads(preview['fields_json'])
        # The generic receipt metadata retains its work routing ID separately
        # from the actual stale-source fingerprint in telegram_preview.expected_json.
        conn.execute('UPDATE telegram_operation SET context_json=?,expected_revision=? WHERE operation_id=?',
                     (actions.packed(context),str(clean['case_id']),operation_id))

    def text(self,summary):
        return ('New task proposal preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nTitle: '+summary['title']+'\nExpected output:\n'+summary['expected_output']
                +'\nContributing unit: '+summary['unit_name']+' (unit '+str(summary['unit_id'])+')'
                +'\nProposed owner: '+summary['owner_name']+(' (account '+str(summary['proposed_owner_id'])+')' if summary['proposed_owner_id'] else '')
                +'\nTask deadline: '+(summary['due_date'] or 'not set')+' · Asia/Manila'
                +'\nCreates one required contribution in proposed status. The concerned officer must confirm its assignment in Office Connect.'
                +'\nNo confirmed owner, progress, submission, acceptance or document approval is created. Existing work review may need to be done again.')

    def check_receipt(self,conn,user,operation):
        if not work.enabled(conn):raise actions.Unavailable('Task proposal receipt unavailable.')
        case_id=number(operation['expected_revision'])
        work.get(conn,user,case_id)
        if operation['target_id']:
            task=work_reads.task(conn,user,case_id,operation['target_id'])
            if task['creator_id']!=user['id']:raise actions.Unavailable('Task proposal receipt unavailable.')

    def receipt_text(self,conn,user,operation):
        case_id=number(operation['expected_revision'])
        if operation['result_code']=='task_deleted':
            return 'The proposed task was deleted in Office Connect. Recovery will not recreate it.\n/work_status '+str(case_id)
        if operation['state']!='committed' or not operation['target_id']:return None
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        return ('Recorded outcome: task proposed; assignment requires officer confirmation.'
                +'\nTask '+str(task['id'])+' · Work '+str(case_id)+'\nCurrent status: '+task['status'].replace('_',' ')
                +'\nOperation: '+operation['operation_id']+'\n/work_status '+str(case_id)+'\n'+links.origin()+'/work/'+str(case_id)
                +'\nRecovery reports current source state; it never creates another task.')


dispatch.register(ACTION,{'prefix':'newtask','start':'/new_task','path':PATH+'create',
                          'confirm':'/newtask_confirm','receipt':'/newtask_receipt'},Adapter())
COMMANDS=('/new_task','/newtask_preview','/newtask_confirm','/newtask_receipt')
