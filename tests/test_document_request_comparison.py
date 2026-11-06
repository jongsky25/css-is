"""Compare source revisions without changing work or widening readership."""
import pytest
import documents as docs
import documents_understanding as understanding
import documents_request_work as proposals
import documents_permissions as permissions
import storage as st
from test_work import workspace
from test_document_request_work import setup
from test_documents_understanding import reviewed


def test_compare_changed_source_to_original_and_independently_edited_work(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    saved=proposals.propose(c,u[0],doc['id'],0,fields)
    c.execute("UPDATE work_task SET expected_output='Internal agreed output',revision=revision+1 WHERE id=?",(saved['task_id'],));c.commit()
    current=docs.get(c,u[0],doc['id'])
    understanding.revise(c,u[0],doc['id'],current['revision'],{
        **reviewed(),'need_0_output':'Updated source output','need_0_deadline':'2026-12-01',
        'focus_evidence':'New focus evidence','reason':'Read revised source','review_confirmed':'yes'})
    changes_before=c.total_changes
    comparison=proposals.comparison(c,u[0],doc['id'],0)
    assert c.total_changes==changes_before
    assert comparison['changed_count']==3
    output=next(r for r in comparison['rows'] if r['label']=='Expected output')
    assert output=={'label':'Expected output','before':'Comments matrix','after':'Updated source output',
                    'work':'Internal agreed output','changed':True,'different':True}
    focus=next(r for r in comparison['rows'] if r['label']=='Focus evidence')
    assert focus['work'] is None
    assert comparison['task']['revision']==2
    assert proposals.existing(c,u[0],doc['id'],0)['changed']


def test_removed_request_preserves_original_and_disabled_modules_allow_read(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    proposals.propose(c,u[0],doc['id'],0,fields)
    current=docs.get(c,u[0],doc['id'])
    understanding.revise(c,u[0],doc['id'],current['revision'],{
        'needs_status':'unclear','reason':'The source does not support this request','review_confirmed':'yes'})
    st.set_setting(c,'documents.enabled','0');st.set_setting(c,'work.enabled','0')
    comparison=proposals.comparison(c,u[0],doc['id'],0)
    assert comparison['removed']
    action=comparison['rows'][0]
    assert action['before']=='Submit comments' and action['after']=='Not recorded'
    assert action['work']=='Submit comments'


def test_unchanged_source_can_differ_from_work_without_claiming_source_change(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    proposals.propose(c,u[0],doc['id'],0,{**fields,'expected_output':'Agreed internal deliverable'})
    result=proposals.comparison(c,u[0],doc['id'],0)
    assert result['changed_count']==0
    assert next(r for r in result['rows'] if r['label']=='Expected output')['different']
    with pytest.raises(permissions.Denied): proposals.comparison(c,u[4],doc['id'],0)
    # Work permission cannot substitute for access to its original source.
    c.execute('DELETE FROM work_document')
    c.execute('UPDATE work_case SET lead_id=?',(u[3]['id'],));c.commit()
    with pytest.raises(permissions.Denied): proposals.comparison(c,u[3],doc['id'],0)
