"""The guidance panel points to available controls without changing the record."""
from html.parser import HTMLParser
import json
import re

import pytest
import storage as st
import documents as d
import documents_operations as ops
from tests.test_documents import Adapter


class Targets(HTMLParser):
    def __init__(self,html):
        super().__init__();self.ids=[];self.links=[];self.feed(html)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='a' and attrs.get('href','').startswith('#'):self.links.append(attrs['href'][1:])


@pytest.fixture
def detail_record(app_mod,viewer):
    c=st.connect(app_mod.DB)
    st.set_setting(c,'documents.enabled','1')
    user=st.get_admin_user(c,'viewer@test.local')
    c.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'records','2026-10-21')",(user['id'],));c.commit()
    doc=d.register(c,user,{'subject':'Guided response','type':'memo','direction':'OUT'})
    doc=d.mutate(c,user,doc['id'],doc['revision'],'verify',{'verification':'verified','reason':'Checked'})
    doc=d.mutate(c,user,doc['id'],doc['revision'],'lead',{'user_id':user['id'],'task':'Coordinate response','reason':'Confirmed ownership'})
    yield c,user,doc,f"/documents/{doc['id']}"
    c.close()


def panel(response):
    assert response.status_code in (200,400),response.text[:1000]
    return re.search(r'<section[^>]+id="document-next".*?</section>',response.text,re.S)[0]


def test_detail_action_targets_exist_and_reads_preserve_workflow(detail_record,viewer,admin,monkeypatch):
    c,user,doc,url=detail_record
    def no_provider(*args,**kwargs):raise AssertionError('A GET called a provider')
    monkeypatch.setattr('documents_workspace.WorkspaceRelay.call',no_provider)
    before=[tuple(r) for r in c.execute('SELECT * FROM document_event WHERE document_id=?',(doc['id'],))]
    response=viewer.get(url)
    guidance=panel(response)
    assert 'What happens next?' in guidance and 'Responsible:' in guidance
    assert 'viewer@test.local' in guidance
    assert 'href="#document-action-attach"' in guidance
    targets=Targets(response.text)
    assert len(targets.ids)==len(set(targets.ids))
    assert all(link in targets.ids for link in Targets(guidance).links)
    assert [tuple(r) for r in c.execute('SELECT * FROM document_event WHERE document_id=?',(doc['id'],))]==before
    assert d.raw(c,doc['id'])['revision']==doc['revision']
    # An administrator's technical role grants no document access.
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],));c.commit()
    assert admin.get(url).status_code==404
    assert 'Guided response' not in admin.get('/documents').text


def test_failed_action_rerenders_fresh_advice_and_escapes_review_feedback(detail_record,viewer):
    c,user,doc,url=detail_record
    doc=ops.attach(c,user,doc['id'],doc['revision'],'https://drive.google.com/file/d/sourcefile12345/view','material','Draft',Adapter())
    # Retained historical feedback is untrusted text, never executable markup.
    c.execute("INSERT INTO document_review(document_id,version_id,actor_id,decision,reason,delegation_json,created_at) VALUES (?,?,?,'changes_requested',?,'[]','2026-10-21')",(doc['id'],doc['current_version'],user['id'],'<script>steal()</script>'))
    c.execute("UPDATE document SET status='changes_requested' WHERE id=?",(doc['id'],));c.commit()
    response=viewer.get(url);csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',response.text)[1]
    assert 'Attach the revised draft' in panel(response)
    assert '<script>steal()</script>' not in response.text
    assert '&lt;script&gt;steal()&lt;/script&gt;' in response.text
    result=viewer.post(url+'/close',data={'csrf':csrf,'revision':doc['revision'],'closure:outcome':'Premature'},follow_redirects=False)
    assert result.status_code==400
    assert 'Attach the revised draft' in panel(result)
    assert d.raw(c,doc['id'])['status']=='changes_requested'


def test_empty_closure_policy_is_distinct_from_missing_policy(detail_record,viewer):
    c,user,doc,url=detail_record
    c.execute("UPDATE document SET direction='IN',policy_json=? WHERE id=?",(json.dumps({'closure':[]}),doc['id']))
    c.execute("UPDATE document_assignment SET status='completed' WHERE document_id=?",(doc['id'],));c.commit()
    response=viewer.get(url)
    assert 'Review closure requirements' in panel(response)
    assert 'No additional closure evidence is required by this policy.' in response.text
    c.execute("UPDATE document SET policy_json='{}' WHERE id=?",(doc['id'],));c.commit()
    response=viewer.get(url)
    assert 'data-stage="closure_policy"' in panel(response)
    assert 'doc-next-action' not in panel(response)


def test_current_role_changes_remove_next_action(detail_record,viewer):
    c,user,doc,url=detail_record
    c.execute("UPDATE document SET verification='pending' WHERE id=?",(doc['id'],));c.commit()
    assert '#document-action-verify' in panel(viewer.get(url))
    c.execute("UPDATE document_role_grant SET revoked_at='2026-10-21' WHERE user_id=? AND role='records'",(user['id'],));c.commit()
    assert '#document-action-verify' not in panel(viewer.get(url))
    st.set_setting(c,'documents.enabled','0');c.commit()
    assert 'data-stage="disabled"' in panel(viewer.get(url))
