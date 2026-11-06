import pytest
import documents as docs
import documents_permissions as permissions
import documents_request_work as proposals
import documents_understanding as understanding
import storage as st
import work
from documents_storage import rows
from test_work import workspace, document
from test_documents_understanding import reviewed


def setup(c,u,unit):
    doc=document(c,u[0],unit,**reviewed())
    fields={'title':'Submit comments','expected_output':'Comments matrix','unit_id':str(unit),
            'due_date':'2026-11-20','revision':str(doc['revision']), 'confirmed':'yes',
            'source_hash':proposals.digest(proposals.source(c,doc['id'],0))}
    return doc,fields


def test_proposal_preserves_evidence_and_does_not_assign_or_change_deadline(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    before=c.execute('SELECT * FROM document_assignment').fetchall()
    result=proposals.propose(c,u[0],doc['id'],0,fields)
    task=rows(c,'SELECT * FROM work_task WHERE id=?',(result['task_id'],))[0]
    assert task['status']=='proposed' and task['owner_id'] is None and task['proposed_owner_id'] is None
    assert work.get(c,u[0],result['case_id'])['lead_id'] is None
    assert result['values']['need_0_evidence']==reviewed()['need_0_evidence']
    assert result['values']['focus_primary']=='governance'
    current=docs.get(c,u[0],doc['id'])
    assert current['due_date']==doc['due_date'] and current['instruction_state']==doc['instruction_state']
    assert c.execute('SELECT * FROM document_assignment').fetchall()==before
    assert proposals.propose(c,u[0],doc['id'],0,fields)['case_id']==result['case_id']
    assert c.execute('SELECT COUNT(*) FROM work_case').fetchone()[0]==1
    with pytest.raises(docs.Conflict):
        proposals.propose(c,u[0],doc['id'],0,{**fields,'title':'Duplicate'})
    st.init_db(c)
    assert proposals.existing(c,u[0],doc['id'],0)['task_id']==task['id']


@pytest.mark.parametrize('change', ['confirmation','unconfirmed','unclear','stale','hash','output','unit','deadline','routing','disabled','closed','denied'])
def test_rejects_without_partial_work(workspace,change):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    actor=u[0]
    if change=='confirmation': fields['confirmed']=''
    if change in ('unconfirmed','unclear'):
        import json
        values=understanding.read(c,doc['id'])
        values['need_0_confirmed' if change=='unconfirmed' else 'need_0_kind']=''
        if change=='unclear': values['need_0_kind']='unclear'
        c.execute('UPDATE document_understanding SET values_json=? WHERE document_id=?',(json.dumps(values),doc['id']));c.commit()
        fields['source_hash']=proposals.digest(proposals.source(c,doc['id'],0))
    if change=='stale': fields['revision']='0'
    if change=='hash': fields['source_hash']='old'
    if change=='output': fields['expected_output']=''
    if change=='unit': fields['unit_id']='0'
    if change=='deadline':
        c.execute("UPDATE document SET due_date='2026-11-19' WHERE id=?",(doc['id'],));c.commit()
    if change=='routing':
        c.execute("UPDATE document SET instruction_state='pending' WHERE id=?",(doc['id'],));c.commit()
    if change=='disabled': st.set_setting(c,'work.enabled','0')
    if change=='closed':
        c.execute("UPDATE document SET status='closed' WHERE id=?",(doc['id'],));c.commit()
    if change=='denied': actor=u[4]
    with pytest.raises((ValueError,permissions.Denied)):
        proposals.propose(c,actor,doc['id'],0,fields)
    for table in ('work_case','work_task','document_request_work'):
        assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    assert docs.get(c,u[0],doc['id'])['revision']==doc['revision']


def test_changed_source_is_visible_without_overwriting_work_and_rechecks_access(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    saved=proposals.propose(c,u[0],doc['id'],0,fields)
    current=docs.get(c,u[0],doc['id'])
    understanding.revise(c,u[0],doc['id'],current['revision'],{**reviewed(),'need_0_output':'New output','review_confirmed':'yes','reason':'Checked source'})
    assert proposals.existing(c,u[0],doc['id'],0)['changed']
    assert work.get(c,u[0],saved['case_id'])['outcome']=='Comments matrix'
    with pytest.raises(permissions.Denied): proposals.existing(c,u[4],doc['id'],0)
    with pytest.raises(docs.Conflict):
        proposals.propose(c,u[0],doc['id'],0,{**fields,'source_hash':proposals.digest(proposals.source(c,doc['id'],0))})


def test_audit_failure_rolls_back_everything(workspace,monkeypatch):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    def fail(*args,**kwargs): raise RuntimeError('audit unavailable')
    monkeypatch.setattr(docs,'finish',fail)
    with pytest.raises(RuntimeError): proposals.propose(c,u[0],doc['id'],0,fields)
    for table in ('work_case','work_task','document_request_work'):
        assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0


def test_concurrent_retry_creates_one_case_and_task(workspace):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    c,u,unit,path=workspace
    doc,fields=setup(c,u,unit)
    start=Barrier(2)
    def submit():
        other=st.connect(path)
        try:
            start.wait(timeout=10)
            return proposals.propose(other,u[0],doc['id'],0,fields)['case_id']
        finally: other.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first=executor.submit(submit)
        second=executor.submit(submit)
        assert first.result(timeout=20)==second.result(timeout=20)
    for table in ('work_case','work_task','document_request_work'):
        assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==1


def test_work_readership_does_not_grant_access_to_unlinked_original_source(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    saved=proposals.propose(c,u[0],doc['id'],0,fields)
    c.execute('DELETE FROM work_document WHERE case_id=?',(saved['case_id'],))
    c.execute('UPDATE work_case SET lead_id=? WHERE id=?',(u[3]['id'],saved['case_id']))
    c.commit()
    assert work.get(c,u[3],saved['case_id'])
    assert proposals.task_source(c,u[3],saved['task_id']) is None
    with pytest.raises(permissions.Denied): proposals.existing(c,u[3],doc['id'],0)
