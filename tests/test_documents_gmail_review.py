"""Gmail review UI, access boundaries, and explicit extraction confirmation."""
import json
import re
import pytest
from fastapi.testclient import TestClient
import auth
import documents as d
import documents_email as email
import documents_operations as ops
import storage as st
from test_documents_email import setup, payload


@pytest.fixture
def review(setup,monkeypatch,tmp_path):
    import app
    import monitoring
    conn,path,uid,_=setup
    monkeypatch.setattr(app,'DB',path)
    monkeypatch.setattr(monitoring,'LOG_PATH',str(tmp_path/'requests.log'))
    st.mark_onboarded(conn,uid)
    result=email.ingest(conn,payload())
    other=st.create_admin_user(conn,'unrelated@example.test','hash','salt','viewer',active=True)
    st.mark_onboarded(conn,other)
    with TestClient(app.app) as client:
        client.cookies.set(auth.COOKIE_NAME,auth.make_token(st.get_admin_user_by_id(conn,uid)))
        yield conn,uid,result['document_id'],other,client


def fields(client,docid):
    page=client.get('/documents/'+str(docid));assert page.status_code==200,page.text
    return {'csrf':re.search(r'name="csrf" value="([a-f0-9]+)"',page.text).group(1),
            'revision':re.search(r'name="revision" value="(\d+)"',page.text).group(1)}


def test_source_badges_filters_export_and_permissions(review):
    c,uid,did,other,client=review
    user=st.get_admin_user_by_id(c,uid)
    manual=d.register(c,user,{'subject':'Manual record','type':'memo'})
    page=client.get('/documents?queue=gmail_review')
    assert 'Imported from Gmail' in page.text and 'Incoming memo' in page.text
    assert 'Manual record' not in page.text
    detail=client.get('/documents/'+str(did))
    assert 'office@example.test' in detail.text and '19abc123' in detail.text
    assert 'Suggest fields from an imported attachment' in detail.text
    assert detail.text.count('<option value=')>=2
    csv=client.get('/documents/export.csv?queue=gmail_review').text
    assert 'Incoming memo' in csv and 'Manual record' not in csv
    client.cookies.set(auth.COOKIE_NAME,auth.make_token(st.get_admin_user_by_id(c,other)))
    assert 'Incoming memo' not in client.get('/documents?queue=gmail_review').text
    assert 'Incoming memo' not in client.get('/documents/export.csv?queue=gmail').text
    assert client.get('/documents/'+str(did)).status_code==404
    # Bureau records authority does not override a restricted record's access.
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(did,));c.commit()
    assert not d.list_visible(c,user,queue='gmail_review')


def test_verification_and_correction_queue_transitions(review):
    c,uid,did,other,client=review
    user=st.get_admin_user_by_id(c,uid)
    def act(action,**data):
        doc=d.raw(c,did);return d.mutate(c,user,did,doc['revision'],action,data)
    act('verify',verification='verified',reason='Checked source')
    assert not d.list_visible(c,user,queue='gmail_review')
    assert len(d.list_visible(c,user,queue='gmail'))==1
    act('verify',verification='needs_correction',reason='Correct classification')
    assert len(d.list_visible(c,user,queue='gmail_review'))==1
    c.execute("UPDATE document SET status='cancelled' WHERE id=?",(did,));c.commit()
    assert not d.list_visible(c,user,queue='gmail_review')


def test_extraction_requires_confirmation_and_retains_source(review,monkeypatch):
    c,uid,did,other,client=review
    source=c.execute('SELECT id FROM document_file_version WHERE document_id=? ORDER BY id DESC',(did,)).fetchone()[0]
    calls=[]
    class Adapter:
        def call(self,action,data,operation):
            calls.append(data)
            return {'state':'confirmed','suggestions':{'subject':'Extracted subject','type':'memorandum','sender':'Office B','due_date':'2026-11-01'},
                    'excerpts':['<script>secret extracted text</script>'],'warnings':[]}
    monkeypatch.setattr(ops,'get_adapter',lambda:Adapter())
    data=fields(client,did)
    assert client.post(f'/documents/{did}/extract',data={'revision':data['revision'],'source_version_id':source}).status_code==403
    response=client.post(f'/documents/{did}/extract',data={**data,'source_version_id':source,'url':'https://evil.test'})
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    assert calls[0]['file_id']=='sourcefile67890'
    assert 'https://drive.google.com/file/d/sourcefile67890/view' in response.text
    assert '&lt;script&gt;' in response.text and '<script>secret extracted text' not in response.text
    doc=d.raw(c,did)
    assert doc['subject']=='Incoming memo' and doc['due_date'] is None and doc['verification']=='pending'
    jobs=c.execute('SELECT payload_json,result_json FROM document_job WHERE document_id=?',(did,)).fetchall()
    assert 'secret extracted text' not in str(jobs) and 'Extracted subject' not in str(jobs)
    confirm={'csrf':data['csrf'],'revision':doc['revision'],'subject':'Extracted subject','type':'memorandum','sender':'Office B','reason':'Compared with source'}
    response=client.post(f'/documents/{did}/confirmed_fields',data=confirm,follow_redirects=False)
    assert response.status_code==303,response.text
    doc=d.raw(c,did)
    assert doc['subject']=='Extracted subject' and doc['verification']=='pending' and doc['due_date'] is None
    assert doc['lead_id'] is None and doc['reconcile']==1
    assert c.execute('SELECT count(*) FROM document_email_import WHERE document_id=?',(did,)).fetchone()[0]==1


def test_attachment_from_another_record_rejected(review,monkeypatch):
    c,uid,did,other,client=review
    user=st.get_admin_user_by_id(c,uid)
    otherdoc=d.register(c,user,{'subject':'Other','type':'memo','drive_url':'https://drive.google.com/file/d/otherfile12345/view'})
    vid=c.execute('SELECT id FROM document_file_version WHERE document_id=?',(otherdoc['id'],)).fetchone()[0]
    monkeypatch.setattr(ops,'get_adapter',lambda:pytest.fail('Should not contact relay'))
    response=client.post(f'/documents/{did}/extract',data={**fields(client,did),'source_version_id':vid})
    assert response.status_code==400
    assert 'Choose an attachment belonging to this record' in response.text
    assert c.execute('SELECT count(*) FROM document_job').fetchone()[0]==0


def test_failure_preserves_manual_correction_and_hides_provider_error(review,monkeypatch):
    c,uid,did,other,client=review
    class Adapter:
        def call(self,*args):raise RuntimeError('PROVIDER_SECRET')
    monkeypatch.setattr(ops,'get_adapter',lambda:Adapter())
    vid=c.execute('SELECT id FROM document_file_version WHERE document_id=?',(did,)).fetchone()[0]
    response=client.post(f'/documents/{did}/extract',data={**fields(client,did),'source_version_id':vid})
    assert response.status_code==400 and 'Correct fields manually' in response.text
    assert 'PROVIDER_SECRET' not in response.text
    assert 'Correct or confirm document fields' in response.text
    assert d.raw(c,did)['subject']=='Incoming memo'
    assert c.execute('SELECT state FROM document_job').fetchone()[0]=='failed'


def test_concurrent_correction_rejects_stale_suggestion_confirmation(review,monkeypatch):
    c,uid,did,other,client=review
    user=st.get_admin_user_by_id(c,uid)
    path=c.execute('PRAGMA database_list').fetchone()[2]
    class Adapter:
        def call(self,*args):
            other_conn=st.connect(path)
            try:
                doc=d.raw(other_conn,did)
                d.mutate(other_conn,user,did,doc['revision'],'confirmed_fields',{'subject':'Concurrent correction','type':'memo','sender':'Office C','reason':'Checked'})
            finally:
                other_conn.close()
            return {'state':'confirmed','suggestions':{'subject':'Old suggestion'},'excerpts':[],'warnings':[]}
    monkeypatch.setattr(ops,'get_adapter',lambda:Adapter())
    data=fields(client,did)
    vid=c.execute('SELECT id FROM document_file_version WHERE document_id=?',(did,)).fetchone()[0]
    response=client.post(f'/documents/{did}/extract',data={**data,'source_version_id':vid})
    assert response.status_code==200,response.text
    revision=re.search(r'name="revision" value="(\d+)"',response.text).group(1)
    result=client.post(f'/documents/{did}/confirmed_fields',data={**data,'revision':revision,'subject':'Old suggestion','type':'memo','sender':'Office','reason':'Checked'})
    assert result.status_code==409
    assert d.raw(c,did)['subject']=='Concurrent correction'
