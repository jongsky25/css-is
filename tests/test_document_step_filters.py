"""Full-scope document counts, independent expected sets and read-only filters."""
import json
from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

import pytest
import documents as docs
import documents_actions as actions
import documents_permissions as permissions
import storage as st
from tests.test_documents import registry
from tests.test_document_registry_pagination import seed_many
from tests.test_document_guidance_routes import detail_record

TODAY='2026-11-07'


def configure(c,uid,did,state,due=None):
    c.execute('''UPDATE document SET lead_id=?,instruction_state='routed',verification=?,
        direction=?,policy_json='{}',due_date=? WHERE id=?''',
        (uid,'pending' if state=='waiting' else 'verified','IN' if state=='attention' else 'OUT',due,did))


def contribution(c,uid,did,due):
    return c.execute('''INSERT INTO document_assignment(document_id,user_id,role,action,status,due_date,created_at)
        VALUES (?,?,'contributor','Synthetic contribution','assigned',?,'2026-11-01')''',(did,uid,due)).lastrowid


def traverse(c,user,state,overdue,expected_counts):
    found=[];before=0;due=''
    while True:
        page=actions.page(c,user,today=TODAY,step_state=state,overdue=overdue,limit=7,before=before,before_due=due)
        assert page['counts']==expected_counts
        ids=list(dict.fromkeys(card['document_id'] for card in page['cards']))
        assert len(ids)==page['document_count']
        found+=ids
        assert all((state=='all' or card['state']==state) and (overdue=='0' or card['overdue']) for card in page['cards'])
        if not page['more']:break
        before,due=page['next_before'],page['next_due']
    assert len(found)==len(set(found))
    return set(found)


def test_full_scope_truth_sets_beyond_pages_and_batches(registry,monkeypatch):
    c,u,unit,_=registry
    ids=seed_many(c,u[0],unit,65)
    expected={state:set() for state in actions.STATES}
    late={state:set() for state in actions.STATES}
    for n,did in enumerate(ids):
        state=('ready','waiting','attention')[n%3]
        due=('2026-11-06','2026-11-07',None)[n%3]
        configure(c,u[0]['id'],did,state,due)
        expected['all'].add(did);expected[state].add(did)
        if due and due<TODAY:late['all'].add(did);late[state].add(did)
    # A ready contribution tomorrow and a waiting workflow yesterday do NOT
    # make the document match Ready + Overdue.
    mixed=ids[1];configure(c,u[0]['id'],mixed,'waiting','2026-11-06')
    contribution(c,u[0]['id'],mixed,'2026-11-08')
    expected['ready'].add(mixed);late['all'].add(mixed);late['waiting'].add(mixed)
    hidden=seed_many(c,u[1],unit,5,visibility='restricted')
    for did in hidden:configure(c,u[1]['id'],did,'ready','2026-11-01')
    c.commit()
    monkeypatch.setattr(actions,'SCAN_BATCH',11)
    before='\n'.join(c.iterdump())
    for overdue,sets in [('0',expected),('1',late)]:
        for state in actions.STATES:
            assert traverse(c,u[0],state,overdue,{k:len(v) for k,v in sets.items()})==sets[state]
    assert '\n'.join(c.iterdump())==before


def test_mixed_attention_and_instruction_counts_overlap(registry):
    c,u,unit,_=registry
    did=seed_many(c,u[0],unit,1)[0];configure(c,u[0]['id'],did,'attention','2026-11-06')
    iid=c.execute("INSERT INTO document_directive(document_id,actor_id,text,created_at) VALUES (?,?,'Read this','2026-11-01')",(did,u[1]['id'])).lastrowid
    c.execute('INSERT INTO document_instruction_recipient VALUES (?,?)',(iid,u[0]['id']))
    c.execute("INSERT INTO document_instruction_tag VALUES (?,'person',?)",(iid,u[0]['id']));c.commit()
    page=actions.page(c,u[0],today=TODAY)
    assert page['counts']=={'all':1,'ready':1,'waiting':0,'attention':1}
    assert len(page['cards'])==2
    st.set_setting(c,'documents.enabled','0');c.commit()
    page=actions.page(c,u[0],today=TODAY)
    assert page['counts']=={'all':1,'ready':0,'waiting':1,'attention':0}
    assert all(card['state']=='waiting' for card in page['cards'])


def test_matching_fourth_child_and_stable_anchor(registry):
    c,u,unit,_=registry
    did=seed_many(c,u[0],unit,1)[0];configure(c,u[0]['id'],did,'ready','2026-11-08')
    # Unknown dates follow explicit deadlines. All children must be classified,
    # but only displayed child bodies should be read.
    for _ in range(3):contribution(c,u[0]['id'],did,None)
    target=contribution(c,u[0]['id'],did,'2026-11-06');c.commit()
    page=actions.page(c,u[0],today=TODAY,step_state='ready',overdue='1')
    assert page['counts']=={'all':1,'ready':1,'waiting':0,'attention':0}
    assert len(page['cards'])==1
    assert page['cards'][0]['anchor']==f'document-step-{did}-contribution-{target}'
    assert page['cards'][0]['detail']=='Synthetic contribution'
    other=actions.page(c,u[0],today=TODAY)
    assert any(x['anchor']==page['cards'][0]['anchor'] for x in other['cards'])


def test_counts_recheck_access_and_exclude_inactive_records(registry):
    c,u,unit,_=registry
    ids=seed_many(c,u[0],unit,6)
    for did in ids:configure(c,u[0]['id'],did,'ready')
    c.execute("UPDATE document SET status='closed' WHERE id=?",(ids[0],))
    c.execute("UPDATE document SET status='cancelled' WHERE id=?",(ids[1],))
    c.execute("UPDATE document SET archived_at='2026-11-01' WHERE id=?",(ids[2],))
    c.execute('UPDATE document SET canonical_id=? WHERE id=?',(ids[5],ids[3]));c.commit()
    first=actions.page(c,u[0],today=TODAY,limit=1)
    assert first['counts']['all']==2
    c.execute("UPDATE document SET visibility='restricted',lead_id=?,creator_id=? WHERE id=?",(u[1]['id'],u[1]['id'],ids[4]));c.commit()
    second=actions.page(c,u[0],today=TODAY,before=first['next_before'],before_due=first['next_due'])
    assert second['counts']['all']==1 and second['cards']==[]
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));c.commit()
    with pytest.raises(permissions.Denied):actions.page(c,u[0],today=TODAY)


@pytest.mark.parametrize('query',['step_state=bad','overdue=yes','view=division&step_state=all'])
def test_invalid_filters_offer_native_recovery(detail_record,viewer,query):
    response=viewer.get('/documents/actions?'+query)
    assert response.status_code==400
    assert 'href="/documents/actions"' in response.text


def test_filter_return_context_survives_actual_save(detail_record,viewer):
    c,user,doc,url=detail_record
    c.execute("UPDATE document SET due_date='2026-01-01' WHERE id=?",(doc['id'],));c.commit()
    response=viewer.get('/documents/actions?step_state=ready&overdue=1')
    assert response.status_code==200 and '1 matching documents' in response.text
    assert response.headers['cache-control']=='private, no-store'
    link=next(unescape(x) for x in re.findall(r'href="([^"]+)"',response.text) if x.startswith(url+'?return_to='))
    origin=parse_qs(urlsplit(link).query)['return_to'][0]
    assert parse_qs(urlsplit(origin).query)=={'step_state':['ready'],'overdue':['1']}
    assert urlsplit(origin).fragment.startswith(f'document-step-{doc["id"]}-')
    detail=viewer.get(link)
    action=next(unescape(x) for x in re.findall(r'action="([^"]+)"',detail.text) if x.startswith(url+'/verify?'))
    csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',detail.text)[1]
    result=viewer.post(action,data={'csrf':csrf,'revision':doc['revision'],'verification':'verified','reason':'Synthetic check'},follow_redirects=False)
    assert result.status_code==303
    assert parse_qs(urlsplit(result.headers['location']).query)['return_to']==[origin]


def test_batched_work_links_match_strict_service_and_aliases(registry):
    import work
    c,u,unit,_=registry
    st.set_setting(c,'work.enabled','1')
    ids=seed_many(c,u[0],unit,3)
    for did in ids:configure(c,u[0]['id'],did,'ready')
    c.commit()
    item=work.create(c,u[0],{'title':'Private work title','outcome':'Synthetic','unit_id':unit,'source_document_id':ids[0]})
    c.execute('INSERT INTO work_document VALUES (?,?,?,?,?)',(item['id'],ids[1],'reference',u[0]['id'],'2026-11-01'))
    # Alias remains a reference to the active document, not a second result.
    c.execute('UPDATE document SET canonical_id=? WHERE id=?',(ids[0],ids[2]))
    c.execute('INSERT INTO work_document VALUES (?,?,?,?,?)',(item['id'],ids[2],'reference',u[0]['id'],'2026-11-01'));c.commit()
    for private in (False,True):
        if private:
            c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(ids[1],));c.commit()
        for user in u:
            scope=permissions.RegistryScope(c,user)
            permitted=[{'id':did} for did in ids[:2] if permissions.can_view(c,user,docs.raw(c,did))]
            if not permitted:continue
            cases=actions._load(c,scope,permitted)[-1]
            for doc in permitted:
                expected=work.cases_for_document(c,user,doc['id'])
                assert [r['id'] for r in cases.get(doc['id'],[])]==[r['id'] for r in expected[:1]]
        page=actions.page(c,u[0],today=TODAY)
        assert 'Private work title' not in json.dumps(page)


def test_early_guidance_does_not_read_consolidation_graph(registry,monkeypatch):
    c,u,unit,_=registry
    did=seed_many(c,u[0],unit,1)[0];configure(c,u[0]['id'],did,'waiting');c.commit()
    def forbidden(*args,**kwargs):raise AssertionError('Early step loaded shared-work graph')
    monkeypatch.setattr(actions.work_review,'summaries',forbidden)
    assert actions.page(c,u[0],today=TODAY)['counts']['waiting']==1


def test_reconciliation_keeps_ready_waiting_semantics(registry):
    c,u,unit,_=registry
    did=seed_many(c,u[0],unit,1)[0];configure(c,u[0]['id'],did,'ready')
    c.execute('UPDATE document SET reconcile=1,reviewer_id=? WHERE id=?',(u[3]['id'],did));c.commit()
    assert actions.page(c,u[0],today=TODAY)['counts']=={'all':1,'ready':1,'waiting':0,'attention':0}
    assert actions.page(c,u[3],today=TODAY)['counts']=={'all':1,'ready':0,'waiting':1,'attention':0}


def test_migrated_legacy_child_cannot_change_overdue_counts(registry):
    import work
    c,u,unit,_=registry
    st.set_setting(c,'work.enabled','1')
    did=seed_many(c,u[0],unit,1)[0];configure(c,u[0]['id'],did,'ready','2026-11-08')
    contribution(c,u[0]['id'],did,'2026-11-01');c.commit()
    item=work.create(c,u[0],{'title':'Migrated work','outcome':'Synthetic','unit_id':unit,'source_document_id':did})
    c.execute("INSERT INTO work_legacy_document VALUES (?,?,?,'Synthetic migration',1,'2026-11-01')",(did,item['id'],u[0]['id']));c.commit()
    page=actions.page(c,u[0],today=TODAY)
    assert page['counts']=={'all':1,'ready':1,'waiting':0,'attention':0}
    assert all(card['kind']!='Contribution' for card in page['cards'])
    assert actions.page(c,u[0],today=TODAY,overdue='1')['counts']==dict.fromkeys(actions.STATES,0)
