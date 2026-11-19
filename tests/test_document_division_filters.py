"""Division counts use current permitted exception scope before page limits."""
import time
import pytest
import storage as st
import documents_actions as actions
import documents_permissions as permissions
from tests.test_documents import registry
from tests.test_document_registry_pagination import seed_many
from tests.test_document_step_filters import configure, contribution
from tests.test_document_guidance_routes import detail_record

TODAY='2026-11-18'


def test_division_counts_filters_and_readonly_pagination(registry,monkeypatch):
    c,u,unit,_=registry
    st.set_section_oic(c,unit,u[3]['id'])
    ids=seed_many(c,u[0],unit,65)
    expected={s:set() for s in actions.STATES}
    for i,did in enumerate(ids):
        state=('ready','waiting','attention')[i%3]
        configure(c,u[3]['id'],did,'attention' if state=='attention' else 'ready','2026-11-01')
        if state=='waiting':c.execute("UPDATE document SET instruction_state='pending' WHERE id=?",(did,))
        expected['all'].add(did);expected[state].add(did)
    hidden=seed_many(c,u[0],unit,4,visibility='restricted')
    outside=st.add_org_unit(c,'Outside','division','BLHSD/OUTSIDE')
    seed_many(c,u[0],outside,4)
    c.commit();monkeypatch.setattr(actions,'SCAN_BATCH',7)
    before_dump='\n'.join(c.iterdump())
    for state in actions.STATES:
        before=0;due='';found=[]
        while True:
            page=actions.page(c,u[3],'division',today=TODAY,limit=5,step_state=state,
                              overdue='1',before=before,before_due=due)
            assert page['counts']=={s:len(v) for s,v in expected.items()}
            found.extend(card['document_id'] for card in page['cards'])
            assert all(card['state']==state or state=='all' for card in page['cards'])
            if not page['more']:break
            before,due=page['next_before'],page['next_due']
        assert set(found)==expected[state] and len(found)==len(set(found))
    assert '\n'.join(c.iterdump())==before_dump
    st.clear_section_oic(c,unit)
    with pytest.raises(permissions.Denied):actions.page(c,u[3],'division',today=TODAY)


def test_unknown_deadline_and_personal_steps_do_not_inflate_division_counts(registry):
    c,u,unit,_=registry;st.set_section_oic(c,unit,u[3]['id'])
    did=seed_many(c,u[0],unit,1)[0]
    contribution(c,u[3]['id'],did,'2026-11-01');c.commit()
    page=actions.page(c,u[3],'division',today=TODAY)
    assert page['counts']['all']==1 and len(page['cards'])==1
    assert actions.page(c,u[3],'division',today=TODAY,overdue='1')['counts']['all']==0
    st.set_setting(c,'documents.enabled','0');c.commit()
    assert actions.page(c,u[3],'division',today=TODAY)['counts']==dict(all=1,ready=0,waiting=1,attention=0)


def test_division_route_preserves_filters_and_scope(detail_record,viewer):
    c,user,doc,url=detail_record
    unit=st.add_org_unit(c,'Division test','division','BLHSD/FILTER')
    st.set_section_oic(c,unit,user['id'])
    ids=seed_many(c,user,unit,34)
    c.execute("UPDATE document SET due_date='2026-01-01' WHERE unit_id=?",(unit,));c.commit()
    response=viewer.get('/documents/actions?view=division&step_state=ready&overdue=1')
    assert response.status_code==200
    assert '34 matching documents' in response.text
    assert 'Filter Division follow-up' in response.text
    assert 'view=division&amp;step_state=ready&amp;overdue=1&amp;before=' in response.text
    assert 'return_to=' in response.text
    assert response.headers['Cache-Control']=='private, no-store'


def test_synthetic_division_scope_benchmark(registry):
    c,u,unit,_=registry;st.set_section_oic(c,unit,u[3]['id'])
    seed_many(c,u[0],unit,1000)
    started=time.perf_counter();page=actions.page(c,u[3],'division',today=TODAY)
    print(f'Division 1000 documents: {time.perf_counter()-started:.3f}s')
    assert page['counts']['all']==1000 and page['document_count']==actions.PAGE_SIZE


from tests.test_document_registration_browser import browser
from tests.test_request_reconciliation_browser import open_page, fits


@pytest.mark.parametrize('scripts',[False,True])
def test_division_phone_filters_page_and_return(browser,detail_record,viewer,scripts):
    c,user,doc,url=detail_record
    unit=st.add_org_unit(c,'Browser division','division','BLHSD/BROWSER')
    st.set_section_oic(c,unit,user['id'])
    seed_many(c,user,unit,34)
    c.execute("UPDATE document SET due_date='2026-01-01' WHERE unit_id=?",(unit,));c.commit()
    writes=[];context,page=open_page(browser,viewer,390,scripts,writes)
    try:
        page.goto('http://office.test/documents/actions?view=division')
        page.get_by_label('Documents with…').select_option('ready')
        page.get_by_label('Overdue only').check()
        page.get_by_role('button',name='Apply filters').focus()
        with page.expect_navigation():page.keyboard.press('Enter')
        assert '34 matching documents' in page.get_by_role('status').inner_text()
        page.get_by_role('link',name='Next page',exact=True).click()
        assert page.locator('.doc-action-card').count()==4
        page.locator('.doc-action-card h3 a').first.click()
        page.locator('.doc-queue-return').click()
        assert 'view=division' in page.url and 'step_state=ready' in page.url and 'overdue=1' in page.url
        assert page.locator('.doc-action-card').count()==4
        assert fits(page) and not writes
    finally:context.close()


from tests.test_work import workspace, consolidation_fixture, request_consolidation
from tests.test_documents import act
import documents as docs
import json


def test_division_private_work_remains_hidden(workspace):
    c,u,unit,_=workspace
    source,doc,item,task=consolidation_fixture(workspace)
    st.set_section_oic(c,unit,u[2]['id'])
    doc=act(c,u[1],doc,'lead',user_id=u[2]['id'],task='Coordinate',reason='Confirmed')
    doc=request_consolidation(c,u,doc,item)
    act(c,u[1],source,'deadline',due_date='2027-01-01',reason='Changed requirement')
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(source['id'],))
    c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(source['id'],u[2]['id']))
    c.execute("UPDATE document SET due_date='2026-01-01' WHERE id=?",(doc['id'],));c.commit()
    page=actions.page(c,u[2],'division',today=TODAY)
    card=next(x for x in page['cards'] if x['document_id']==doc['id'])
    assert card['url']==f"/documents/{doc['id']}#document-next"
    assert item['title'] not in json.dumps(page)
    assert source['id'] not in {x['document_id'] for x in page['cards']}
    # State counts are those of the permitted document guidance, not hidden work.
    expected={s:0 for s in actions.STATES}
    for row in page['cards']:expected['all']+=1;expected[row['state']]+=1
    assert page['counts']==expected
