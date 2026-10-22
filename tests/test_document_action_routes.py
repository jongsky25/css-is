"""HTTP paging and safe recovery links use the actual document routes."""
from html import unescape
import re

import pytest
import storage as st
import documents as d
import documents_actions as actions
import documents_operations as ops
from tests.test_document_guidance_routes import detail_record
from tests.test_document_registry_pagination import seed_many
from tests.test_documents import Adapter


def test_action_pages_keep_scope_in_navigation_and_never_call_provider(detail_record,viewer,admin,monkeypatch):
    c,user,doc,url=detail_record
    seed_many(c,user,None,actions.PAGE_SIZE+2,subject='Paged response')
    def no_provider(*args,**kwargs):raise AssertionError('GET contacted a provider')
    monkeypatch.setattr('documents_workspace.WorkspaceRelay.call',no_provider)
    before=[tuple(x) for x in c.execute('SELECT id,revision FROM document')]
    response=viewer.get('/documents/actions')
    assert response.status_code==200
    assert f'{actions.PAGE_SIZE} documents on this page' in response.text
    assert 'Ready for you' in response.text
    href=unescape(re.search(r'<a href="([^"]+)" rel="next">Next page',response.text)[1])
    second=viewer.get(href)
    assert second.status_code==200 and 'First page' in second.text
    assert '3 documents on this page' in second.text
    assert 'Paged response' not in admin.get('/documents/actions').text
    assert [tuple(x) for x in c.execute('SELECT id,revision FROM document')]==before
    assert viewer.get('/documents/actions?view=division').status_code==403
    for query in ['before=-1','before=no','before=1','before=1&due=bad','due=2026-10-20','view=invalid']:
        assert viewer.get('/documents/actions?'+query).status_code==400


def test_cards_escape_untrusted_instructions_and_task_text(detail_record,viewer):
    c,user,doc,url=detail_record
    text='<script>steal()</script>'
    c.execute('UPDATE document_assignment SET action=? WHERE document_id=?',(text,doc['id']))
    iid=c.execute("INSERT INTO document_directive(document_id,actor_id,text,created_at) VALUES (?,?,?,'2026-10-21')",(doc['id'],user['id'],text)).lastrowid
    c.execute('INSERT INTO document_instruction_recipient VALUES (?,?)',(iid,user['id']))
    c.execute("INSERT INTO document_instruction_tag VALUES (?,'person',?)",(iid,user['id']));c.commit()
    page=viewer.get('/documents/actions')
    assert page.status_code==200
    assert text not in page.text and '&lt;script&gt;steal()&lt;/script&gt;' in page.text
    assert f'#instruction-{iid}' in page.text
    aid=c.execute('SELECT id FROM document_assignment WHERE document_id=?',(doc['id'],)).fetchone()[0]
    assert f'#document-contribution-{aid}' in page.text


def review_ready(c,user,doc):
    bureau=st.add_org_unit(c,'Reviewer Bureau','bureau','ACTION/REVIEW')
    rp=st.add_rp(c,'Current reviewer',is_internal=True,org_unit_id=bureau)
    c.execute("UPDATE resource_person SET position='Director' WHERE id=?",(rp,))
    c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,user['id']));c.commit()
    doc=ops.attach(c,user,doc['id'],doc['revision'],'https://drive.google.com/file/d/sourcefile12345/view','material','Draft',Adapter())
    doc=d.mutate(c,user,doc['id'],doc['revision'],'review_route',{'review_class':'director','reviewer_id':user['id'],'reason':'Confirmed authority'})
    return doc,rp


def test_stale_review_card_loses_its_form_after_authority_revocation(detail_record,viewer):
    c,user,doc,url=detail_record
    doc,rp=review_ready(c,user,doc)
    assert '#document-action-review"' in viewer.get('/documents/actions').text
    c.execute("UPDATE resource_person SET position='Staff' WHERE id=?",(rp,));c.commit()
    page=viewer.get(url+'#document-action-review')
    assert page.status_code==200
    assert 'data-stage="review_authority"' in page.text
    assert 'id="document-action-review"' not in page.text
    csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
    result=viewer.post(url+'/review',data={'csrf':csrf,'revision':doc['revision'],'decision':'approved','reason':'Old form'},follow_redirects=False)
    assert result.status_code==403
    assert d.raw(c,doc['id'])['approved_version'] is None
