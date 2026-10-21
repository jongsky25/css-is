"""A15: current workflow cards, permission-before-limit paging and batch reads."""
import json
import uuid

import pytest
import storage as st
import documents as d
import documents_actions as actions
import documents_operations as ops
import documents_permissions as p
from tests.test_documents import registry, register, act, approved, Adapter
from tests.test_documents_guidance import view
from tests.test_document_registry_pagination import seed_many
from tests.test_work import workspace, consolidation_fixture, request_consolidation


def workflow(c,user,doc):
    cards=actions.page(c,user)['cards']
    return next(card for card in cards if card['document_id']==doc['id'] and card['kind'] not in ('Instruction','Contribution'))


def assert_guidance(c,user,doc):
    advice=view(c,user,doc);card=workflow(c,user,doc)
    assert card['detail']==advice['message']
    assert card['owner_id']==advice['owner_id']
    assert card['owner_role']==advice['owner_role']
    href=advice['action']['href'] if advice['action'] else '#document-next'
    expected=f"/documents/{doc['id']}"+href if href.startswith('#') else href
    assert card['url']==expected
    return card


def test_card_journey_matches_document_correction_revision_and_current_review(registry):
    c,u,unit,_=registry
    doc=approved(registry)
    assert assert_guidance(c,u[2],doc)['url'].endswith('#document-action-sign_preview')
    doc=act(c,u[1],doc,'review_route',review_class='director',reviewer_id=u[2]['id'],reason='Renew review')
    card=assert_guidance(c,u[2],doc)
    assert card['state']=='ready' and card['url'].endswith('#document-action-review')
    doc=act(c,u[2],doc,'review',decision='changes_requested',reason='Correct the annex')
    assert assert_guidance(c,u[0],doc)['url'].endswith('#document-action-attach')
    doc=ops.attach(c,u[0],doc['id'],doc['revision'],'https://drive.google.com/file/d/newdraft12345/view','material','Revised',Adapter())
    assert assert_guidance(c,u[1],doc)['url'].endswith('#document-action-review_route')
    doc=act(c,u[1],doc,'verify',verification='needs_correction',reason='Check sender')
    assert assert_guidance(c,u[0],doc)['url'].endswith('#document-action-confirmed_fields')
    doc=act(c,u[0],doc,'confirmed_fields',subject=doc['subject'],type=doc['type'],sender='Correct office',reason='Source checked')
    card=assert_guidance(c,u[0],doc)
    assert card['state']=='waiting' and card['owner_role']=='Concerned records officer'


def test_stale_reviewer_role_does_not_advertise_review(registry):
    c,u,unit,_=registry
    doc=approved(registry)
    doc=act(c,u[1],doc,'review_route',review_class='director',reviewer_id=u[2]['id'],reason='Renew review')
    c.execute("UPDATE resource_person SET position='Staff' WHERE id=(SELECT rp_id FROM admin_user WHERE id=?)",(u[2]['id'],));c.commit()
    card=assert_guidance(c,u[2],doc)
    assert card['state']=='attention' and not card['url'].endswith('#document-action-review')
    with pytest.raises(p.Denied):act(c,u[2],doc,'review',decision='approved',reason='Old authority')


@pytest.mark.parametrize('state',['pending','running','unknown'])
def test_uncertain_effects_show_receipts_and_pause_contributions(registry,state):
    c,u,unit,_=registry
    doc=approved(registry)
    doc=act(c,u[1],doc,'lead',user_id=u[1]['id'],task='Coordinate response',reason='Confirmed assignment')
    op=ops.queue(c,u[2],doc['id'],doc['revision'],'sign',{'confirmed_fingerprint':'v1'})
    c.execute('UPDATE document_job SET state=? WHERE id=?',(state,op));c.commit()
    card=assert_guidance(c,u[1],doc)
    assert card['state']=='attention' and card['url'].endswith('#document-operations')
    assert 'do not resend' in card['detail']
    contributions=[x for x in actions.page(c,u[1])['cards'] if x['kind']=='Contribution']
    assert contributions and all(x['state']=='waiting' and x['url'].endswith('#document-next') for x in contributions)


def test_partial_unknown_and_historical_delivery_advice(registry):
    c,u,unit,_=registry;doc=approved(registry)
    doc=ops.external_signature(c,u[2],doc['id'],doc['revision'],'https://drive.google.com/file/d/signedfile12345/view','v1','Signed',Adapter())
    payload={'channel':'email','sender':'office@example.test','recipients':['a@example.test','b@example.test']}
    doc=ops.persist_dispatch(c,u[1],doc,payload,str(uuid.uuid4()),{'a@example.test':{'outcome':'accepted'},'b@example.test':{'outcome':'failed'}},'Receipt checked');c.commit()
    card=assert_guidance(c,u[1],doc)
    assert card['state']=='attention' and card['url'].endswith('#document-recipient-outcomes')
    c.execute("UPDATE document_dispatch_recipient SET outcome='unknown' WHERE recipient='b@example.test'");c.commit()
    assert 'Do not resend' in assert_guidance(c,u[1],doc)['detail']
    doc=ops.attach(c,u[0],doc['id'],doc['revision'],'https://drive.google.com/file/d/newdraft12345/view','material','Changed',Adapter())
    assert assert_guidance(c,u[1],doc)['url'].endswith('#document-action-review_route')


def test_pending_initial_instruction_blocks_contribution_even_before_verification(registry):
    c,u,unit,_=registry
    doc=register(c,u[0],unit)
    c.execute("UPDATE document SET instruction_state='pending' WHERE id=?",(doc['id'],))
    c.execute("INSERT INTO document_assignment(document_id,user_id,role,action,status,created_at) VALUES (?,?,'contributor','Prepare annex','assigned','2026-10-21')",(doc['id'],u[0]['id']));c.commit()
    cards=actions.page(c,u[0])['cards']
    contribution=next(x for x in cards if x['kind']=='Contribution')
    assert contribution['state']=='waiting' and contribution['url'].endswith('#document-next')
    assert 'verification' in contribution['blocker']


def test_pagination_deadlines_ties_unknowns_and_hidden_rows_before_limit(registry):
    c,u,unit,_=registry
    records=[]
    for n,due in enumerate(['2026-10-19','2026-10-21',None,'2026-10-19',None,'2026-11-01','2026-10-21']):
        records.append(register(c,u[0],unit,'OUT',subject=f'Visible {n}',due_date=due))
    for n in range(6):
        hidden=register(c,u[1],unit,'OUT',subject=f'Hidden {n}',due_date='2026-01-01')
        c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(hidden['id'],));c.commit()
    c.commit()
    expected=sorted(records,key=lambda x:(x['due_date'] or '9999-12-31',-x['id']))
    seen=[];before=0;due=''
    while True:
        page=actions.page(c,u[0],limit=2,before=before,before_due=due,today='2026-10-20')
        ids=list(dict.fromkeys(x['document_id'] for x in page['cards']))
        assert len(ids)==page['document_count']<=2
        assert all('Hidden' not in x['subject'] for x in page['cards'])
        seen.extend(ids)
        if not page['more']:break
        before,due=page['next_before'],page['next_due']
    assert seen==[x['id'] for x in expected]
    assert len(seen)==len(set(seen))
    assert any(x['due_label']=='Deadline unknown' and not x['overdue'] for x in page['cards'])


def test_cursor_never_carries_authority_and_archived_closed_merged_are_excluded(registry):
    c,u,unit,_=registry
    docs=[register(c,u[0],unit,'OUT') for _ in range(6)]
    c.execute("UPDATE document SET archived_at='2026-10-21' WHERE id=?",(docs[0]['id'],))
    c.execute("UPDATE document SET status='closed' WHERE id=?",(docs[1]['id'],))
    c.execute('UPDATE document SET canonical_id=? WHERE id=?',(docs[3]['id'],docs[2]['id']));c.commit()
    page=actions.page(c,u[0],limit=1)
    assert page['more']
    target=docs[4]
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(target['id'],));c.commit()
    after=actions.page(c,u[0],before=page['next_before'],before_due=page['next_due'])
    assert all(x['document_id']!=target['id'] for x in after['cards'])
    assert actions.page(c,u[4])['cards']==[]  # Technical admin has no document grant.
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));c.commit()
    with pytest.raises(p.Denied):actions.page(c,u[0],before=page['next_before'],before_due=page['next_due'])


def test_batch_queries_do_not_grow_with_total_records_and_child_bodies_are_capped(registry):
    c,u,unit,_=registry
    seed_many(c,u[0],unit,40)
    def measured():
        statements=[];c.set_trace_callback(statements.append)
        try:page=actions.page(c,u[0],limit=5)
        finally:c.set_trace_callback(None)
        return page,[x for x in statements if x.lstrip().upper().startswith(('SELECT','WITH'))]
    first,small=measured()
    seed_many(c,u[0],unit,600)
    second,large=measured()
    assert first['document_count']==second['document_count']==5
    assert len(small)==len(large) and len(large)<45
    did=second['cards'][0]['document_id']
    for n in range(15):
        c.execute("INSERT INTO document_assignment(document_id,user_id,role,action,status,created_at) VALUES (?,?,'contributor',?,'assigned','2026-10-21')",(did,u[0]['id'],'Task '+str(n)))
        iid=c.execute("INSERT INTO document_directive(document_id,actor_id,text,created_at) VALUES (?,?,?,'2026-10-21')",(did,u[1]['id'],'Instruction '+str(n))).lastrowid
        c.execute('INSERT INTO document_instruction_recipient VALUES (?,?)',(iid,u[0]['id']))
        c.execute("INSERT INTO document_instruction_tag VALUES (?,'person',?)",(iid,u[0]['id']))
    c.commit()
    before='\n'.join(c.iterdump())
    page=actions.page(c,u[0],limit=1)
    assert len(page['cards'])==1+2*actions.CHILD_LIMIT
    assert len([x for x in page['cards'] if x['kind']=='Instruction'])==actions.CHILD_LIMIT
    assert len([x for x in page['cards'] if x['kind']=='Contribution'])==actions.CHILD_LIMIT
    assert '\n'.join(c.iterdump())==before


def test_consolidation_links_require_current_work_access(workspace):
    c,u,unit,_=workspace
    source,doc,item,task=consolidation_fixture(workspace)
    doc=act(c,u[1],doc,'lead',user_id=u[2]['id'],task='Coordinate',reason='Confirmed')
    doc=request_consolidation(c,u,doc,item)
    assert assert_guidance(c,u[2],doc)['url'].endswith('#document-action-review')
    act(c,u[1],source,'deadline',due_date='2027-01-01',reason='Changed requirement')
    doc=d.raw(c,doc['id'])
    card=assert_guidance(c,u[2],doc)
    assert card['state']=='attention' and card['url']==f"/work/{item['id']}/consolidation"
    # A named document reviewer can remain able to see the official output
    # after losing access to a restricted source of the shared work item.
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(source['id'],))
    c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(source['id'],u[2]['id']));c.commit()
    card=workflow(c,u[2],doc)
    assert card['url']==f"/documents/{doc['id']}#document-next"
    assert item['title'] not in json.dumps(card)


def test_division_pages_filter_scope_before_limit_and_recheck_oic(registry):
    c,u,unit,_=registry
    st.set_section_oic(c,unit,u[3]['id'])
    other=st.add_org_unit(c,'Other','division','BLHSD/D2')
    for i in range(7):register(c,u[0],other,'OUT',due_date='2026-01-01')
    own=[register(c,u[0],unit,'OUT',due_date='2026-10-18') for _ in range(4)]
    c.execute("UPDATE document SET verification='verified',visibility='bureau'");c.commit()
    page=actions.page(c,u[3],'division',limit=2,today='2026-10-20')
    assert {x['document_id'] for x in page['cards']}=={d['id'] for d in own[-2:]}
    st.clear_section_oic(c,unit)
    with pytest.raises(p.Denied):actions.page(c,u[3],'division',before=page['next_before'],before_due=page['next_due'])


def test_disabled_module_never_labels_business_actions_ready(registry):
    c,u,unit,_=registry;doc=approved(registry)
    st.set_setting(c,'documents.enabled','0');c.commit()
    cards=actions.page(c,u[1])['cards']
    assert cards and all(x['state']=='waiting' for x in cards)
    assert all('read-only' in (x['detail']+str(x['blocker'])) or 'disabled' in (x['detail']+str(x['blocker'])) for x in cards)


@pytest.mark.parametrize('kwargs',[{'before':-1},{'before':'oops'},{'before':2**64},
    {'before':1},{'before':1,'before_due':'bad'},{'before_due':'2026-10-20'},
    {'limit':0},{'limit':51},{'limit':True}])
def test_invalid_action_pages_fail_closed(registry,kwargs):
    c,u,unit,_=registry
    with pytest.raises(ValueError):actions.page(c,u[0],**kwargs)


def test_action_statements_parse_on_system_sqlite(registry,tmp_path):
    """Deployment SQLite's parser must accept the real permission/page SQL."""
    import sqlite3
    import subprocess
    from pathlib import Path
    c,u,unit,_=registry
    register(c,u[0],unit,'OUT')
    captured=[]
    for user in u:
        statements=[];c.set_trace_callback(statements.append)
        try:actions.page(c,user,limit=2)
        finally:c.set_trace_callback(None)
        for sql in statements:
            if 'action_candidates AS' in sql or 'WITH numbered AS' in sql or 'WITH RECURSIVE aliases' in sql:
                captured.append({'sql':sql,'expected':[tuple(r) for r in c.execute(sql)]})
    db=tmp_path/'action-parser.db'
    with sqlite3.connect(db) as destination:c.backup(destination)
    corpus=tmp_path/'statements.json';corpus.write_text(json.dumps(captured))
    program='''import json,sqlite3,sys
from pathlib import Path
c=sqlite3.connect(Path(sys.argv[1]).as_uri()+'?mode=ro',uri=True)
cases=json.loads(Path(sys.argv[2]).read_text())
for case in cases:
    actual=[list(row) for row in c.execute(case['sql'])]
    assert actual==case['expected']
print(len(cases))
'''
    result=subprocess.run(['/usr/bin/python3','-c',program,str(db),str(corpus)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert int(result.stdout)>=5


def test_previous_requester_keeps_recovery_card_when_latest_job_has_another_actor(registry):
    c,u,unit,_=registry;doc=approved(registry)
    for ident,actor in [('00000000-0000-4000-8000-000000000001',u[3]),('ffffffff-ffff-4fff-8fff-ffffffffffff',u[1])]:
        c.execute("INSERT INTO document_job(id,document_id,actor_id,kind,version_id,payload_json,state,created_at,updated_at) VALUES (?,?,?,'dispatch',?,'{}','pending','2026-10-21','2026-10-21')",(ident,doc['id'],actor['id'],doc['current_version']))
    c.commit()
    card=workflow(c,u[3],doc)
    assert card['state']=='attention' and card['url'].endswith('#document-operations')
