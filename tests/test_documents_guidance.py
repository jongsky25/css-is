"""Next-step journeys use real lifecycle gates, with no provider calls on reads."""
import json
import uuid

import pytest
import storage as st
import documents as d
import documents_guidance as guidance
import documents_operations as ops
import documents_permissions as p
import work
import work_review
from documents_storage import rows
from tests.test_documents import registry, register, act, policy, approved, Adapter
from tests.test_work import workspace


def view(c,user,doc):
    user=p.actor(c,user)
    doc=d.get(c,user,doc['id'])
    officer=p.officer(c,user,doc)
    assignments=rows(c,'SELECT * FROM document_assignment_effective WHERE document_id=?',(doc['id'],))
    for a in assignments:
        a['progress_choices']=[('submitted','Submit for consolidation')] if a['user_id']==user['id'] and a['status'] not in ('completed','superseded') else []
    return guidance.build(c,user,{'doc':doc,'policy':json.loads(doc['policy_json']),
        'officer':officer,'can_work':p.can_work(c,user,doc),'can_release':p.can_release(c,user,doc),
        'can_archive':p.has_role(c,user,'workflow_admin',doc['unit_id']),
        'signatory':p.has_role(c,user,'signatory',doc['unit_id']),
        'assignments':assignments,'assignments_migrated':False,
        'versions':rows(c,'SELECT * FROM document_file_version WHERE document_id=?',(doc['id'],)),
        'jobs':rows(c,'SELECT * FROM document_job WHERE document_id=?',(doc['id'],)),
        'dispatches':rows(c,'SELECT * FROM document_dispatch WHERE document_id=?',(doc['id'],)),
        'recipient_outcomes':rows(c,'SELECT r.* FROM document_dispatch_recipient r JOIN document_dispatch x ON x.id=r.dispatch_id WHERE x.document_id=?',(doc['id'],)),
        'consolidation':work_review.summaries(c,user,[doc]).get(doc['id']),
        'work_cases':work.cases_for_document(c,user,doc['id'])})


def stage(c,user,doc,name,action=None):
    before='\n'.join(c.iterdump())
    result=view(c,user,doc)
    assert result['stage']==name,result
    if action is not None:
        assert result['action']['href']=='#document-action-'+action,result
    assert '\n'.join(c.iterdump())==before  # Advice must not advance a workflow.
    return result


def finish_assignments(c,user,doc):
    for a in rows(c,"SELECT * FROM document_assignment WHERE document_id=? AND status NOT IN ('completed','superseded')",(doc['id'],)):
        doc=act(c,user,doc,'contribution',assignment_id=a['id'],status='completed',outcome='Consolidated')
    return doc


def test_correction_and_incoming_completion_reopen_journey(registry):
    c,u,unit,_=registry
    policy(c,u[1],u[1]['id'])
    doc=register(c,u[0],unit,'OUT')
    stage(c,u[1],doc,'verification','verify')
    assert view(c,u[0],doc)['action'] is None
    doc=act(c,u[1],doc,'verify',verification='needs_correction',reason='Check sender')
    stage(c,u[0],doc,'correction','confirmed_fields')
    doc=act(c,u[0],doc,'confirmed_fields',subject=doc['subject'],type=doc['type'],sender='Correct office',reason='Source checked')
    stage(c,u[1],doc,'verification','verify')
    doc=act(c,u[1],doc,'verify',verification='verified',reason='checked')
    stage(c,u[1],doc,'reconcile','reconcile')
    doc=act(c,u[1],doc,'reconcile',reason='Confirmed source and routing')
    # An incoming record can close only after the same retained evidence gates.
    incoming=register(c,u[0],unit)
    c.execute("UPDATE document SET instruction_state='pending' WHERE id=?",(incoming['id'],));c.commit()
    incoming=d.raw(c,incoming['id'])
    incoming=act(c,u[1],incoming,'verify',verification='verified',reason='Checked source')
    stage(c,u[2],incoming,'instruction','route_instruction')
    incoming=act(c,u[2],incoming,'route_instruction',lead_id=u[1]['id'],unit_id=unit,reason='Respond to the request')
    stage(c,u[1],incoming,'contributions')
    incoming=finish_assignments(c,u[1],incoming)
    stage(c,u[1],incoming,'close','close')
    with pytest.raises(ValueError,match='closure evidence'):
        act(c,u[1],incoming,'close',evidence={})
    incoming=act(c,u[1],incoming,'close',evidence={'outcome':'Request resolved'})
    stage(c,u[1],incoming,'complete','reopen')
    incoming=act(c,u[1],incoming,'reopen',due_date='2027-01-15',reason='New information')
    stage(c,u[1],incoming,'reconcile','reconcile')


def test_review_return_signature_delivery_acknowledgment_and_closure(registry):
    c,u,unit,_=registry
    doc=approved(registry)
    stage(c,u[2],doc,'signature','sign_preview')
    assert view(c,u[0],doc)['action'] is None
    # A material revision invalidates approval and must re-enter review.
    doc=ops.attach(c,u[0],doc['id'],doc['revision'],'https://drive.google.com/file/d/newdraft12345/view','material','Revised content',Adapter())
    stage(c,u[1],doc,'approval','review_route')
    doc=act(c,u[1],doc,'review_route',review_class='director',reviewer_id=u[2]['id'],reason='Renewed review')
    stage(c,u[2],doc,'review','review')
    assert view(c,u[0],doc)['action'] is None
    doc=act(c,u[2],doc,'review',decision='changes_requested',reason='<script>Revise the conclusion</script>')
    stage(c,u[0],doc,'revision','attach')
    doc=ops.attach(c,u[0],doc['id'],doc['revision'],'https://drive.google.com/file/d/revised12345/view','material','Addressed comments',Adapter())
    doc=act(c,u[1],doc,'review_route',review_class='director',reviewer_id=u[2]['id'],reason='Corrections checked')
    doc=act(c,u[2],doc,'review',decision='approved',reason='Reviewed exact draft')
    doc=ops.external_signature(c,u[2],doc['id'],doc['revision'],'https://drive.google.com/file/d/signedfile12345/view','v1','Signed final',Adapter())
    stage(c,u[1],doc,'release','record_dispatch')
    st.set_setting(c,'documents.official_sender','office@example.test');st.set_setting(c,'documents.sending_enabled','1');c.commit()
    operation=ops.queue(c,u[1],doc['id'],doc['revision'],'dispatch',{'channel':'direct_email','recipients':['a@example.test'],'checklist':{'authority':'checked'}})
    result=stage(c,u[1],doc,'operation')
    assert result['action']['href']=='#document-operations'
    assert 'do not resend' in result['message']
    ops.execute(c,operation,Adapter());doc=d.raw(c,doc['id'])
    # Mandatory contributions and acknowledgments are independent closure gates.
    doc=finish_assignments(c,u[1],doc)
    stage(c,u[1],doc,'acknowledgment','acknowledge')
    did=c.execute('SELECT id FROM document_dispatch WHERE operation_id=?',(operation,)).fetchone()[0]
    doc=ops.acknowledge(c,u[1],doc['id'],doc['revision'],did,'a@example.test','Recipient confirmed receipt')
    stage(c,u[1],doc,'close','close')
    doc=act(c,u[1],doc,'close',evidence={'outcome':'Released and acknowledged'})
    stage(c,u[1],doc,'complete','reopen')


def test_revoked_reviewer_authority_and_stale_revision(registry):
    c,u,unit,_=registry
    doc=approved(registry)
    doc=act(c,u[1],doc,'review_route',review_class='director',reviewer_id=u[2]['id'],reason='Review again')
    c.execute("UPDATE resource_person SET position='Staff' WHERE id=(SELECT rp_id FROM admin_user WHERE id=?)",(u[2]['id'],));c.commit()
    assert view(c,u[2],doc)['action'] is None
    stage(c,u[1],doc,'review_authority','review_route')
    with pytest.raises(p.Denied):
        act(c,u[2],doc,'review',decision='approved',reason='Old authority')
    old=doc
    doc=act(c,u[1],doc,'deadline',due_date='2027-01-01',reason='Authorized')
    with pytest.raises(d.Conflict):
        act(c,u[1],old,'review_route',review_class='director',reviewer_id=u[2]['id'],reason='Stale page')


@pytest.mark.parametrize('state',['pending','running','unknown'])
def test_interrupted_requests_offer_receipts_without_replaying(registry,state):
    c,u,unit,_=registry
    doc=approved(registry)
    operation=ops.queue(c,u[2],doc['id'],doc['revision'],'sign',{'confirmed_fingerprint':'v1'})
    c.execute('UPDATE document_job SET state=? WHERE id=?',(state,operation));c.commit()
    result=stage(c,u[0],doc,'operation')
    assert result['action']['href']=='#document-operations'
    assert result['contributions']==[]


def test_partial_and_unknown_delivery_never_offer_blind_resend(registry):
    c,u,unit,_=registry
    doc=approved(registry)
    doc=ops.external_signature(c,u[2],doc['id'],doc['revision'],'https://drive.google.com/file/d/signedfile12345/view','v1','Signed',Adapter())
    payload={'channel':'direct_email','sender':'office@example.test','recipients':['a@example.test','b@example.test']}
    doc=ops.persist_dispatch(c,u[1],doc,payload,str(uuid.uuid4()),{'a@example.test':{'outcome':'accepted'},'b@example.test':{'outcome':'failed'}},'Checked');c.commit()
    result=stage(c,u[1],doc,'delivery_partial')
    assert result['action']['href']=='#document-recipient-outcomes'
    c.execute("UPDATE document_dispatch_recipient SET outcome='unknown' WHERE recipient='b@example.test'");c.commit()
    stage(c,u[1],doc,'delivery_unknown')
    # Prior-version receipts do not become current delivery advice.
    doc=ops.attach(c,u[0],doc['id'],doc['revision'],'https://drive.google.com/file/d/newdraft12345/view','material','New content',Adapter())
    stage(c,u[1],doc,'approval','review_route')


def test_disabled_archived_and_private_records(registry):
    c,u,unit,_=registry
    doc=register(c,u[0],unit)
    doc=act(c,u[1],doc,'access',visibility='restricted',viewers=[u[0]['id']],reason='Private record')
    with pytest.raises(p.Denied):view(c,u[4],doc)
    st.set_setting(c,'documents.enabled','0');c.commit()
    assert stage(c,u[0],doc,'disabled')['action'] is None
    st.set_setting(c,'documents.enabled','1')
    c.execute("UPDATE document SET archived_at='2026-10-21',status='closed',visibility='restricted' WHERE id=?",(doc['id'],));c.commit()
    assert stage(c,u[0],doc,'archived')['action'] is None
    assert stage(c,u[1],doc,'archived','restore')['action']
    # Registration explicitly grants concerned officers access. Revoking that
    # access must hide even an archived record from the workflow administrator.
    c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],u[1]['id']));c.commit()
    with pytest.raises(p.Denied):view(c,u[1],doc)


def test_structural_closure_advice_matches_domain_gates(registry):
    c,u,unit,_=registry
    policy(c,u[1],u[1]['id'])
    doc=register(c,u[0],unit)
    doc=act(c,u[1],doc,'verify',verification='verified',reason='checked')
    doc=finish_assignments(c,u[1],doc)
    for closure,expected in [(None,'closure_policy'),(['released_reply'],'reply'),([], 'close')]:
        config={'closure':closure} if closure is not None else {}
        c.execute('UPDATE document SET policy_json=? WHERE id=?',(json.dumps(config),doc['id']));c.commit();doc=d.raw(c,doc['id'])
        stage(c,u[1],doc,expected)
        if closure is None:
            with pytest.raises(ValueError,match='configure closure'):
                act(c,u[1],doc,'close',evidence={})
        elif closure:
            with pytest.raises(ValueError,match='reply must be released'):
                act(c,u[1],doc,'close',evidence={'released_reply':'Claim without a linked released reply'})
    assert act(c,u[1],doc,'close',evidence={})['status']=='closed'


def test_consolidation_guidance_hides_private_work_and_tracks_changed_inputs(workspace):
    from tests.test_work import consolidation_fixture, request_consolidation
    c,u,unit,_=workspace
    source,doc,item,task=consolidation_fixture(workspace)
    doc=request_consolidation(c,u,doc,item)
    # This fixture has no document lead; use the responsible lead confirmed by
    # the real document lead action, then renew the changed input snapshot.
    doc=act(c,u[1],doc,'lead',user_id=u[2]['id'],task='Coordinate response',reason='Confirmed responsibility')
    doc=request_consolidation(c,u,doc,item)
    stage(c,u[2],doc,'review','review')
    # The viewer can read the output but is not a member of the work item.
    doc=act(c,u[1],doc,'access',visibility='bureau',viewers=[],reason='Shared official output')
    advice=view(c,u[3],doc)
    assert advice['stage']=='consolidation'
    assert advice['action'] is None
    assert str(item['id']) not in json.dumps(advice)
    assert item['title'] not in json.dumps(advice)
    # A changed source invalidates the review and links only authorized members.
    act(c,u[1],source,'deadline',due_date='2027-02-01',reason='Changed response scope')
    advice=view(c,u[2],doc)
    assert advice['stage']=='consolidation'
    assert advice['action']['href']==f"/work/{item['id']}/consolidation"
