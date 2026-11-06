"""Actual session/CSRF endpoints for review history and correction."""
import re
import pytest
import storage as st
import documents as docs
import documents_understanding as understanding
from test_documents_routes import token
from test_documents_understanding import reviewed
from test_document_understanding_review import correction


@pytest.fixture
def review_record(app_mod,viewer):
    conn=st.connect(app_mod.DB)
    st.set_setting(conn,'documents.enabled','1')
    user=st.get_admin_user(conn,'viewer@test.local')
    doc=docs.register(conn,user,{'subject':'Incoming interpretation','type':'Letter',**reviewed()})
    yield conn,user,doc,f"/documents/{doc['id']}/understanding"
    conn.close()


def test_review_routes_save_history_csrf_and_access(review_record,viewer,admin):
    conn,user,doc,url=review_record
    page=viewer.get(url)
    assert page.status_code==200 and page.headers['cache-control']=='no-store'
    assert 'Original intake review' in page.text
    assert re.search(r'name="need_0_confirmed"[^>]*checked',page.text) is None
    assert viewer.post(url,data={'revision':doc['revision'],**correction()}).status_code==403
    assert admin.get(url).status_code==404
    payload={'csrf':token(page),'revision':doc['revision'],**correction(need_0_output='Corrected deliverable')}
    saved=viewer.post(url,data=payload,follow_redirects=False)
    assert saved.status_code==303
    detail=viewer.get(f"/documents/{doc['id']}")
    assert 'Corrected deliverable' in detail.text
    history=viewer.get(url)
    assert 'Comments matrix' in history.text and 'Corrected deliverable' in history.text
    assert 'Review 2' in history.text and user['username'] in history.text
    assert admin.get(url).status_code==404
    stale=viewer.post(url,data={**payload,'need_0_output':'Stale private edit'})
    assert stale.status_code==409 and 'Stale private edit' in stale.text
    assert understanding.read(conn,doc['id'])['need_0_output']=='Corrected deliverable'
    assert f'name="revision" value="{doc["revision"]}"' in stale.text


def test_validation_keeps_entries_and_escapes_content(review_record,viewer):
    conn,user,doc,url=review_record
    payload={'csrf':token(viewer.get(url)),'revision':doc['revision'],**correction(need_0_confirmed='',need_0_output='<script>alert(1)</script>')}
    response=viewer.post(url,data=payload)
    assert response.status_code==400 and '&lt;script&gt;' in response.text
    assert '<script>alert(1)</script>' not in response.text
    assert understanding.read(conn,doc['id'])['need_0_output']=='Comments matrix'


def test_disabled_module_and_frozen_document_history_remain_readonly(review_record,viewer):
    conn,user,doc,url=review_record
    csrf=token(viewer.get(url))
    st.set_setting(conn,'documents.enabled','0')
    page=viewer.get(url)
    assert page.status_code==200 and 'This review is read-only' in page.text
    response=viewer.post(url,data={'csrf':csrf,'revision':doc['revision'],**correction()})
    assert response.status_code==400
    assert conn.execute('SELECT COUNT(*) FROM document_understanding_revision').fetchone()[0]==0
    st.set_setting(conn,'documents.enabled','1')
    conn.execute("UPDATE document SET status='closed' WHERE id=?",(doc['id'],));conn.commit()
    page=viewer.get(url)
    assert 'This review is read-only' in page.text and 'Original intake review' in page.text
    assert viewer.post(url,data={'csrf':csrf,'revision':doc['revision'],**correction()}).status_code==403


def test_invalid_revision_and_history_cursor_fail_cleanly(review_record,viewer):
    conn,user,doc,url=review_record
    csrf=token(viewer.get(url))
    for revision in ([],{},True,None):
        assert viewer.post(url,json={'csrf':csrf,'revision':revision,**correction()}).status_code==400
    for cursor in ('bad','9'*30,'<script>alert(1)</script>'):
        result=viewer.get(url,params={'before':cursor})
        assert result.status_code==400 and '<script>' not in result.text
