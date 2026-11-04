"""Own supply drafts using native requester/catalog rules and private confirmation."""
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from documents_storage import rows
import supplies
import supplies_requests as requests
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch

ACTION='supplies.draft'
MODES={'create':ACTION}
PATH='/account/telegram/supply-draft/'
LINE_COUNT=5
FIELDS={'create':('purpose','date_needed',*(key for i in range(1,LINE_COUNT+1) for key in ('item_'+str(i),'quantity_'+str(i))))}


def choices(conn,user,mode,values):
    supplies.require_enabled(conn);requests.requester(conn,user)
    query=values.get('q','').strip()
    if len(query)>80 or any(ord(ch)<32 for ch in query):raise actions.Unavailable('Use a catalog search up to 80 characters.')
    after=supplies.integer(values.get('after','0') or '0','Catalog page')
    found=rows(conn,'''SELECT id,code,description,unit,revision FROM supply_item WHERE active=1 AND id>?
        AND (?='' OR instr(lower(code),lower(?))>0 OR instr(lower(description),lower(?))>0)
        ORDER BY id LIMIT 26''',(after,query,query,query))
    options=found[:25];ids={item['id'] for item in options}
    # Retain selected active choices when redisplaying a failed POST from another page.
    for i in range(1,LINE_COUNT+1):
        try:identifier=supplies.integer(values.get('item_'+str(i),''),'Item',1)
        except ValueError:continue
        if identifier not in ids:
            selected=rows(conn,'SELECT id,code,description,unit,revision FROM supply_item WHERE id=? AND active=1',(identifier,))
            if selected:options.extend(selected);ids.add(identifier)
    return {'line_numbers':range(1,LINE_COUNT+1),'catalog_items':options,'catalog_query':query,
            'next_after':found[24]['id'] if len(found)>25 else None}


class Adapter:
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS['create']):raise actions.Unavailable('Complete only the supported supply draft fields.')
        supplies.require_enabled(conn)
        _,identity=requests.requester(conn,user)
        lines=[]
        for i in range(1,LINE_COUNT+1):
            item=raw['item_'+str(i)];quantity=raw['quantity_'+str(i)]
            if item==quantity=='':continue
            lines.append({'item_id':supplies.integer(item,'Item',1),'requested_quantity':supplies.integer(quantity,'Quantity',1)})
        clean=requests._fields({'purpose':supplies.text(raw['purpose'],'Purpose',1000),'date_needed':raw['date_needed'],'lines':lines})
        catalog=[]
        for line in clean['lines']:
            item=supplies.get_item(conn,user,line['item_id'])
            if not item['active']:raise actions.Unavailable('Choose currently active catalog items.')
            catalog.append({key:item[key] for key in ('id','code','description','unit','revision')})
        requests._within_requestable(conn,clean['lines'],None)
        labels=[identity['requester_snapshot'],identity['unit_snapshot'],clean['purpose'],*(item[key] for item in catalog for key in ('code','description','unit'))]
        if any(not isinstance(label,str) or any(unicodedata.category(ch).startswith('C') for ch in label) for label in labels):
            raise actions.Unavailable('This exact preview contains unsupported control characters. Use Office Connect or correct the source labels.')
        summary={'requester':identity,'fields':clean,'items':catalog}
        if common.units(self.text(summary))>3200:raise actions.Unavailable('This exact private preview is too long. Use fewer lines, a shorter purpose or Office Connect.')
        return clean,summary,{'requester':identity,'items':catalog}

    def revalidate(self,conn,user,clean,expected):
        raw={'purpose':clean['purpose'],'date_needed':clean['date_needed'] or ''}
        for i in range(1,LINE_COUNT+1):
            line=clean['lines'][i-1] if i<=len(clean['lines']) else None
            raw.update({'item_'+str(i):line['item_id'] if line else '',
                        'quantity_'+str(i):line['requested_quantity'] if line else ''})
        current,_,fresh=self.prepare(conn,user,raw)
        if current!=clean or fresh!=expected:raise actions.Unavailable('Requester or catalog changed. Prepare a fresh exact draft preview.')

    def text(self,summary):
        identity=summary['requester'];fields=summary['fields']
        text=('Supply draft preview\nRequester: '+identity['requester_snapshot']+'\nUnit: '+identity['unit_snapshot']
              +'\nPurpose: '+fields['purpose']+'\nDate needed: '+(fields['date_needed'] or 'not set'))
        for line,item in zip(fields['lines'],summary['items']):
            text+='\nItem '+str(item['id'])+' · '+item['code']+' · '+item['description']+'\nQuantity: '+str(line['requested_quantity'])+' · Unit: '+item['unit']
        return text+'\nSave one new draft for your linked account only. No control number, submission, approval, stock reservation/issue or approver notification. Review and submit separately in Office Connect.'

    def queue_preview(self,conn,user,operation_id,context,now):
        conn.execute('UPDATE telegram_operation SET context_json=? WHERE operation_id=?',(actions.packed(context),operation_id))

    def apply(self,conn,user,clean,operation_id):
        result=requests.save_draft_in_transaction(conn,user,clean,operation_key=str(uuid5(NAMESPACE_URL,'telegram-supply-draft:'+operation_id)))
        conn.execute('UPDATE telegram_operation SET target_id=?,expected_revision=? WHERE operation_id=?',
                     (result['id'],str(result['revision']),operation_id))
        return {'state':'committed','result_code':'supply_draft_saved'}

    def check_receipt(self,conn,user,operation):
        supplies.require_enabled(conn);requests.requester(conn,user)
        if operation['result_code']=='supply_deleted':return
        if operation['state']=='committed':requests._owned(conn,user,operation['target_id'])

    def receipt_text(self,conn,user,operation):
        self.check_receipt(conn,user,operation)
        if operation['result_code']=='supply_deleted':return 'The saved supply request was deleted. Recovery will not recreate it or use a replacement with the same number.'
        if operation['state']!='committed':return None
        current=requests._owned(conn,user,operation['target_id'])
        return ('Recorded outcome: supply draft saved.\nRequest '+str(current['id'])+' · Saved revision '+operation['expected_revision']
                +'\nCurrent status: '+current['approval_status']+' · Current revision '+str(current['revision'])
                +'\n'+links.origin()+'/supplies/requests/'+str(current['id'])
                +'\nRecovery reports the original draft save and current state; it never creates another draft, overwrites edits or submits a request.')


dispatch.register(ACTION,{'prefix':'supplydraft','start':'/supply_draft','path':PATH+'create',
                         'confirm':'/supplydraft_confirm','receipt':'/supplydraft_receipt'},Adapter())
COMMANDS=('/supply_draft','/supplydraft_preview','/supplydraft_confirm','/supplydraft_receipt')
