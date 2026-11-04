"""Own draft/returned supply submissions through exact private confirmation."""
import json
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from documents_storage import rows
import supplies
import supplies_requests as requests
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import tzutil as tz

ACTION='supplies.submit'
MODES={'submit':ACTION}
PATH='/account/telegram/supply-submit/'
FIELDS={'submit':('request_id','revision')}


def domain_key(operation_id):return str(uuid5(NAMESPACE_URL,'telegram-supply-submit:'+operation_id))


def snapshot(conn,user,clean):
    supplies.require_enabled(conn)
    _,identity=requests.requester(conn,user)
    request=requests._owned(conn,user,clean['request_id'])
    requests._check_revision(request,clean['revision'])
    if request['approval_status'] not in ('draft','returned'):raise actions.Unavailable('Only your draft or returned request can be submitted.')
    lines=rows(conn,'SELECT * FROM supply_request_draft_line WHERE request_id=? AND active=1 ORDER BY id',(request['id'],))
    requests._fields({**request,'lines':lines});requests._active_items(conn,lines)
    requests._within_requestable(conn,lines,request['id'])
    selected=[]
    for line in lines:
        item=supplies._item(conn,line['item_id'])
        if any(line[key+'_snapshot']!=item[key] for key in ('code','description','unit')):
            raise actions.Unavailable('Save current catalog descriptions and units in the native draft before submitting.')
        selected.append({'line_id':line['id'],'item_id':item['id'],'revision':item['revision'],
                         'code':item['code'],'description':item['description'],'unit':item['unit'],
                         'quantity':line['requested_quantity']})
    approvers=sorted(actor['id'] for actor in requests.eligible_approvers(conn,user['id'],identity['unit_id']))
    return {'request':request,'requester':identity,'lines':selected,'approvers':approvers,'year':tz.today_local().year}


def summary_for(state):
    return {'id':state['request']['id'],'revision':state['request']['revision'],'status':state['request']['approval_status'],
            'control':state['request']['control_number'],'purpose':state['request']['purpose'],
            'date_needed':state['request']['date_needed'],'requester':state['requester'],'lines':state['lines'],
            'approver_count':len(state['approvers']),'submitted_version':state['request']['current_revision']+1}


class Adapter:
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS['submit']):raise actions.Unavailable('Choose only your request and exact current revision.')
        clean={key:supplies.integer(raw[key],key,1) for key in FIELDS['submit']}
        if clean['revision']>=2147483647:raise actions.Unavailable('Request revision is outside this pilot. Use Office Connect.')
        state=snapshot(conn,user,clean);summary=summary_for(state)
        labels=[summary['purpose'],summary['requester']['requester_snapshot'],summary['requester']['unit_snapshot'],
                *(line[key] for line in state['lines'] for key in ('code','description','unit'))]
        if any(not isinstance(label,str) or any(unicodedata.category(ch).startswith('C') for ch in label) for label in labels):
            raise actions.Unavailable('This exact private preview has unsupported control characters. Use Office Connect or correct the source.')
        if common.units(self.text(summary))>3200:raise actions.Unavailable('The complete exact submission preview is too long. Submit this request in Office Connect.')
        return clean,summary,state

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:raise actions.Unavailable('Request, catalog, requester, routing or numbering year changed. Prepare a fresh preview.')

    def text(self,summary):
        who=summary['requester']
        text=('Supply submission preview\nRequest '+str(summary['id'])+' · Revision '+str(summary['revision'])+' · '+summary['status']
              +'\nRequester: '+who['requester_snapshot']+'\nUnit: '+who['unit_snapshot']
              +'\nPurpose: '+summary['purpose']+'\nDate needed: '+(summary['date_needed'] or 'not set'))
        for line in summary['lines']:
            text+='\nItem '+str(line['item_id'])+' · '+line['code']+' · '+line['description']+'\nQuantity: '+str(line['quantity'])+' · Unit: '+line['unit']
        text+='\nControl number: '+(summary['control']+' (retained)' if summary['control'] else 'assigned only on confirmation')
        text+='\nNew submitted version: '+str(summary['submitted_version'])+'\nEligible unit approvers (excluding you): '+str(summary['approver_count'])
        if not summary['approver_count']:text+='\nWARNING: No eligible approver is configured for this unit. Submission can wait without an approver.'
        return text+'\nSubmit exactly this request for native unit approval. Normal approval notices are queued; delivery is separate. No approval, reservation or stock issue. Request fields cannot be edited here.'

    def queue_preview(self,conn,user,operation_id,context,now):
        clean=json.loads(rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]['fields_json'])
        conn.execute('UPDATE telegram_operation SET target_id=?,context_json=? WHERE operation_id=?',
                     (clean['request_id'],actions.packed(context),operation_id))

    def apply(self,conn,user,clean,operation_id):
        result=requests.submit_in_transaction(conn,user,clean['request_id'],expected_revision=clean['revision'],operation_key=domain_key(operation_id))
        conn.execute('UPDATE telegram_operation SET expected_revision=? WHERE operation_id=?',(str(result['revision']),operation_id))
        return {'state':'committed','result_code':'supply_submitted'}

    def saved(self,conn,user,operation):
        requests._owned(conn,user,operation['target_id'])
        key=domain_key(operation['operation_id'])
        found=rows(conn,"SELECT * FROM supply_operation WHERE operation_key=? AND actor_id=? AND action='request_submit'",(key,user['id']))
        version=rows(conn,'SELECT * FROM supply_request_revision WHERE operation_key=?',(key,))
        events=rows(conn,"SELECT detail_json FROM supply_event WHERE operation_key=? AND actor_id=? AND action='request_submit' AND entity_type='request' AND entity_id=?",
                    (key,user['id'],operation['target_id']))
        if not found or not version or not events:raise actions.Unavailable('The original supply submission receipt is unavailable.')
        result=json.loads(found[0]['result_json']);detail=json.loads(events[0]['detail_json'])
        if (result['id']!=operation['target_id'] or str(result['revision'])!=operation['expected_revision']
                or version[0]['request_id']!=result['id'] or version[0]['revision']!=result['current_revision']):
            raise actions.Unavailable('The original supply submission receipt is unavailable.')
        return result,version[0],detail

    def check_receipt(self,conn,user,operation):
        supplies.require_enabled(conn);requests.requester(conn,user)
        if operation['result_code']=='supply_deleted':return
        if operation['state']=='committed':self.saved(conn,user,operation)
        else:requests._owned(conn,user,operation['target_id'])

    def receipt_text(self,conn,user,operation):
        self.check_receipt(conn,user,operation)
        if operation['result_code']=='supply_deleted':return 'The source request was deleted. Recovery will not recreate or submit another record with the same number.'
        if operation['state']!='committed':return None
        result,version,detail=self.saved(conn,user,operation);current=requests._owned(conn,user,result['id'])
        count=detail['eligible_approver_count']
        text=('Recorded outcome: supply request submitted for approval.\nRequest '+str(result['id'])+' · '+result['control_number']
              +'\nRecorded submitted version '+str(result['current_revision'])+' · Request revision '+str(result['revision'])
              +'\nOriginal approval unit: '+version['unit_snapshot']+'\nOriginal eligible unit approvers: '+str(count)+'\nCurrent status: '+current['approval_status']+' · Current revision '+str(current['revision']))
        if not count:text+='\nWARNING: No eligible approver was configured at submission; routing may need attention in Office Connect.'
        return text+'\n'+links.origin()+'/supplies/requests/'+str(result['id'])+'\nThis is the original submission, not approval or a stock hold. Recovery never resubmits, consumes another number or overwrites later changes.'


dispatch.register(ACTION,{'prefix':'supplysubmit','start':'/supply_submit','path':PATH+'submit',
                         'confirm':'/supplysubmit_confirm','receipt':'/supplysubmit_receipt'},Adapter())
COMMANDS=('/supply_submit','/supplysubmit_preview','/supplysubmit_confirm','/supplysubmit_receipt')
