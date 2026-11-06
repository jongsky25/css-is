import documents as docs
import documents_request_work as proposals
import documents_understanding as understanding
import storage as st
from test_work import workspace
from test_document_request_work import setup
from test_documents_understanding import reviewed


def test_overview_identifies_gaps_and_counts_current_requests(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    changes=c.total_changes
    result=proposals.overview(c,u[0],doc['id'])
    assert c.total_changes==changes
    assert result['request_count']==1 and result['needs_review']==0
    assert result['visible_work_count']==0 and result['focus_confirmed']
    item=result['items'][0]
    assert item['can_propose'] and item['confirmed']
    assert 'Requested from' in item['missing'] and 'Expected output' not in item['missing']
    st.set_setting(c,'work.enabled','0')
    assert proposals.overview(c,u[0],doc['id'])['items'][0]['url'] is None


def test_cleared_request_keeps_accessible_work_and_changed_warning(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    proposals.propose(c,u[0],doc['id'],0,fields)
    current=docs.get(c,u[0],doc['id'])
    understanding.revise(c,u[0],doc['id'],current['revision'],{
        'needs_status':'unclear','reason':'Unsupported request','review_confirmed':'yes'})
    st.set_setting(c,'work.enabled','0')
    result=proposals.overview(c,u[0],doc['id'])
    assert result['request_count']==0 and result['visible_work_count']==1
    item=result['items'][0]
    assert item['removed'] and item['task']['status']=='Proposed' and item['task']['changed']
    assert item['url'] and not item['can_propose']
    assert not result['focus']


def test_document_reader_cannot_see_unavailable_work_or_cleared_receipt(workspace):
    c,u,unit,_=workspace
    doc,fields=setup(c,u,unit)
    proposals.propose(c,u[0],doc['id'],0,fields)
    c.execute("INSERT INTO document_access VALUES (?,?,'manual')",(doc['id'],u[3]['id']));c.commit()
    result=proposals.overview(c,u[3],doc['id'])
    assert result['request_count']==1 and result['visible_work_count']==0
    assert result['items'][0]['url'] is None and result['items'][0]['task'] is None
    current=docs.get(c,u[0],doc['id'])
    understanding.revise(c,u[0],doc['id'],current['revision'],{
        'needs_status':'unclear','reason':'Unsupported request','review_confirmed':'yes'})
    assert proposals.overview(c,u[3],doc['id'])['items']==[]


def test_unclear_interpretation_needs_review_and_never_offers_proposal(workspace):
    c,u,unit,_=workspace
    doc=docs.register(c,u[0],{'subject':'Unclear source','type':'Letter','unit_id':unit,
        **reviewed(),'need_0_kind':'unclear','focus_primary':'','focus_confirmed':''})
    result=proposals.overview(c,u[0],doc['id'])
    assert result['needs_review']==1
    assert not result['items'][0]['can_propose'] and not result['focus']
