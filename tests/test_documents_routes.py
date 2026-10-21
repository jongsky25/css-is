from tests.conftest import session_token
import re
import storage as st
import documents as d
from io import BytesIO


def token(response):
    found=re.search(r'name="csrf" value="([a-f0-9]+)"',response.text)
    assert found,response.text[:1000]
    return found.group(1)


def test_routes_disabled_csrf_and_private_records(app_mod,viewer,admin):
    c=st.connect(app_mod.DB);st.init_db(c)
    old=st.get_setting(c,'documents.enabled','0')
    try:
        st.set_setting(c,'documents.enabled','0')
        page=viewer.get('/documents');assert page.status_code==200
        assert 'Documents is not enabled' in page.text
        st.set_setting(c,'documents.enabled','1')
        page=viewer.get('/documents/new');assert page.status_code==200
        csrf=token(page)
        assert viewer.post('/documents/new',data={'subject':'Hidden document','type':'memo'}).status_code==403
        created=viewer.post('/documents/new',data={'submission_id':re.search(r'name="submission_id" value="([^"]+)"',page.text)[1],'csrf':csrf,'subject':'Hidden document','type':'memo'},follow_redirects=False)
        assert created.status_code==303,created.text
        url=created.headers['location'];detail=viewer.get(url)
        assert detail.status_code==200,detail.text
        assert 'Hidden document' in detail.text
        assert admin.get(url).status_code==404
        assert 'Hidden document' not in admin.get('/documents').text
        assert 'Hidden document' not in admin.get('/documents/export.csv').text
        # Token from another session cannot mutate the document.
        forged=admin.post(url+'/cancel',data={'csrf':csrf,'revision':'1','reason':'no'},follow_redirects=False)
        assert forged.status_code in (403,404)
        st.set_setting(c,'documents.enabled','0')
        assert viewer.get(url).status_code==200
        assert viewer.post(url+'/in_action',data={'csrf':csrf,'revision':'1','reason':'start'}).status_code==400
    finally:
        st.set_setting(c,'documents.enabled',old);c.close()


def test_rule_screen_requires_explicit_workflow_grant(app_mod,admin):
    assert admin.get('/documents/rules').status_code==403


def test_action_screen_renders_only_permitted_documents(app_mod,viewer,admin):
    c=st.connect(app_mod.DB);st.init_db(c)
    old=st.get_setting(c,'documents.enabled','0')
    try:
        st.set_setting(c,'documents.enabled','1')
        user=st.get_admin_user(c,'viewer@test.local')
        doc=d.register(c,user,{'subject':'Action screen route record','type':'memo','direction':'OUT'})
        c.execute("UPDATE document SET lead_id=?,reconcile=1 WHERE id=?",(user['id'],doc['id']))
        c.commit()
        page=viewer.get('/documents/actions')
        assert page.status_code==200 and 'Action screen route record' in page.text
        assert 'Verify the source and document details' in page.text
        assert 'Waiting' in page.text  # Verification precedes reconciliation.
        assert 'Action screen route record' not in admin.get('/documents/actions').text
        assert viewer.get('/documents/actions?view=division').status_code==403
        assert viewer.get('/documents/actions?view=invalid').status_code==400
    finally:
        st.set_setting(c,'documents.enabled',old);c.close()


def test_memo_annotation_and_file_text_routes(app_mod,viewer,admin,monkeypatch):
    from docx import Document
    import documents_operations as ops
    c=st.connect(app_mod.DB);st.init_db(c)
    old=st.get_setting(c,'documents.enabled','0')
    try:
        st.set_setting(c,'documents.enabled','1')
        user=st.get_admin_user(c,'viewer@test.local')
        doc=d.register(c,user,{'subject':'Enhancement route record','type':'memo','direction':'OUT'})
        url=f"/documents/{doc['id']}"
        detail=viewer.get(url)
        assert 'Start from a memorandum template' in detail.text
        response=viewer.post(url+'/memo.docx',data={'csrf':token(detail),'kind':'internal',
            'to':'Team','from':'Office','date':'2026-10-19','subject':'Draft',
            'body':'Please review the plan.'})
        assert response.status_code==200
        assert 'Please review the plan.' in [p.text for p in Document(BytesIO(response.content)).paragraphs]
        assert admin.post(url+'/memo.docx',data={'csrf':token(detail),'kind':'internal'}).status_code==403
        vid=c.execute('''INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,actor_id,created_at)
            VALUES (?,?,?,?,?,?,?)''',(doc['id'],'https://drive.google.com/file/d/sourcefile12345/view',
            'sourcefile12345','','reference',user['id'],'2026-10-19')).lastrowid
        c.commit()
        note_page=viewer.get(f'{url}/annotate/{vid}')
        assert note_page.status_code==200
        assert admin.get(f'{url}/annotate/{vid}').status_code==404
        saved=viewer.post(f'{url}/annotate/{vid}',data={'csrf':token(note_page),
            'revision':doc['revision'],'kind':'note','page_number':2,'body':'Check this page.'},follow_redirects=False)
        assert saved.status_code==303
        assert 'Check this page.' in viewer.get(f'{url}/annotate/{vid}').text
        class Drive:
            def call(self,action,payload,operation):
                if action=='inspect':
                    return {'accessible':True,'file_id':'sourcefile12345',
                            'fingerprint':'drive-v3:sourcefile12345:1',
                            'mime':'application/pdf','sha256':'a'*64}
                assert action=='text' and payload['fingerprint']=='drive-v3:sourcefile12345:1'
                return {'state':'confirmed','file_id':'sourcefile12345',
                        'fingerprint':payload['fingerprint'],'text':'The uniqueptolemy appendix.'}
        monkeypatch.setattr(ops,'get_adapter',lambda:Drive())
        detail=viewer.get(url)
        indexed=viewer.post(url+'/index-file',data={'csrf':token(detail),'revision':d.raw(c,doc['id'])['revision'],
            'version_id':vid},follow_redirects=False)
        assert indexed.status_code==303
        assert 'Enhancement route record' in viewer.get('/documents?q=uniqueptolemy').text
        assert 'Enhancement route record' not in admin.get('/documents?q=uniqueptolemy').text
        annotation=viewer.get(f'{url}/annotate/{vid}')
        ink={'csrf':token(annotation),'revision':d.raw(c,doc['id'])['revision'],
             'kind':'ink','page_number':1,'strokes':[[[.1,.1],[.2,.2]]],'source_sha256':'a'*64}
        assert viewer.post(f'{url}/annotate/{vid}',json={**ink,'source_sha256':'b'*64}).status_code==400
        assert viewer.post(f'{url}/annotate/{vid}',json=ink,follow_redirects=False).status_code==303
        assert 'Pen marks' in viewer.get(f'{url}/annotate/{vid}').text
    finally:
        st.set_setting(c,'documents.enabled',old);c.close()


def test_instruction_mentions_render_and_require_session_token(app_mod,viewer,admin):
    c=st.connect(app_mod.DB);st.init_db(c)
    old=st.get_setting(c,'documents.enabled','0')
    try:
        st.set_setting(c,'documents.enabled','1')
        user=st.get_admin_user(c,'viewer@test.local')
        doc=d.register(c,user,{'subject':'Instruction mention route','type':'memo','direction':'OUT'})
        url=f"/documents/{doc['id']}"
        page=viewer.get(url)
        assert page.status_code==200 and 'Write an instruction or update' in page.text
        assert 'document_mentions.js' in page.text
        data={'revision':doc['revision'],'reason':'Please check <script>alert(1)</script>',
              f'mention_person:{user["id"]}':'yes'}
        assert viewer.post(url+'/instruction_note',data=data).status_code==403
        saved=viewer.post(url+'/instruction_note',data={**data,'csrf':token(page)},follow_redirects=False)
        assert saved.status_code==303,saved.text
        detail=viewer.get(url)
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in detail.text
        assert '<script>alert(1)</script>' not in detail.text
        search=viewer.get('/documents?q=script')
        assert 'Instruction mention route' in search.text
        assert '&lt;script&gt;' in search.text and '<script>alert(1)</script>' not in search.text
        assert 'Instruction mention route' not in admin.get('/documents?q=script').text
        assert viewer.get('/documents?q=%22+OR+%2A').status_code==200
        assert 'Mark instruction read' not in detail.text  # Authors already saw their own note.
        directive_id=c.execute("SELECT id FROM document_directive WHERE document_id=? AND kind='note'",(doc['id'],)).fetchone()[0]
        read=viewer.post(url+'/instruction_read',data={'csrf':token(detail),'revision':d.raw(c,doc['id'])['revision'],
            'directive_id':directive_id},follow_redirects=False)
        assert read.status_code==303
        assert 'Mark instruction read' not in viewer.get(url).text
    finally:
        st.set_setting(c,'documents.enabled',old);c.close()


def test_archive_screen_and_restore_require_document_admin(app_mod,viewer,admin):
    c=st.connect(app_mod.DB);st.init_db(c)
    old=st.get_setting(c,'documents.enabled','0')
    try:
        st.set_setting(c,'documents.enabled','1')
        admin_user=st.get_admin_user(c,'admin@test.local')
        viewer_user=st.get_admin_user(c,'viewer@test.local')
        for role in ('records','workflow_admin'):
            c.execute('INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)',
                      (admin_user['id'],role,'2026-10-17'))
        c.commit()
        doc=d.register(c,viewer_user,{'subject':'Archive route record','type':'memo'})
        page=admin.get(f"/documents/{doc['id']}")
        csrf=token(page)
        cancelled=admin.post(f"/documents/{doc['id']}/cancel",data={
            'csrf':csrf,'revision':doc['revision'],'reason':'Withdrawn'},follow_redirects=False)
        assert cancelled.status_code==303
        current=d.raw(c,doc['id'])
        denied=viewer.post(f"/documents/{doc['id']}/archive",data={
            'csrf':token(viewer.get(f"/documents/{doc['id']}")),
            'revision':current['revision'],'reason':'Unauthorized'},follow_redirects=False)
        assert denied.status_code==403
        page=admin.get(f"/documents/{doc['id']}")
        assert 'Archive this record' in page.text
        archived=admin.post(f"/documents/{doc['id']}/archive",data={
            'csrf':token(page),'revision':current['revision'],'reason':'Filed'},follow_redirects=False)
        assert archived.status_code==303
        assert 'Archive route record' not in admin.get('/documents').text
        assert 'Archive route record' in admin.get('/documents?queue=archived').text
        assert 'Archive route record' not in admin.get('/documents/export.csv').text
        assert 'Restore from archive' in admin.get(f"/documents/{doc['id']}").text
        current=d.raw(c,doc['id'])
        restored=admin.post(f"/documents/{doc['id']}/restore",data={
            'csrf':token(admin.get(f"/documents/{doc['id']}")),
            'revision':current['revision'],'reason':'Needed again'},follow_redirects=False)
        assert restored.status_code==303
        assert 'Archive route record' in admin.get('/documents').text
    finally:
        c.execute("DELETE FROM document_role_grant WHERE user_id=? AND role IN ('records','workflow_admin') AND created_at='2026-10-17'",
                  (admin_user['id'],))
        c.commit();st.set_setting(c,'documents.enabled',old);c.close()


def test_signature_preview_and_confirm_use_existing_profile(app_mod,monkeypatch):
    import auth
    import documents_operations as ops
    from starlette.testclient import TestClient
    c=st.connect(app_mod.DB);st.init_db(c)
    old=st.get_setting(c,'documents.enabled','0')
    uid=st.create_admin_user(c,'document-signer-http@example.test','unused','unused','viewer',active=True)
    st.mark_onboarded(c,uid);st.set_user_signature(c,uid,b'profile-image','image/png')
    user=st.get_admin_user_by_id(c,uid)
    c.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'signatory','2026-10-15')",(uid,));c.commit()
    st.set_setting(c,'documents.enabled','1')
    doc=d.register(c,user,{'subject':'Sign preview HTTP','type':'memo','direction':'OUT'})
    vid=c.execute("INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,actor_id,created_at) VALUES (?,?,?,?,?,?,?)",
                  (doc['id'],'https://drive.google.com/file/d/sourcefile12345/view','sourcefile12345','v1','draft',uid,'2026-10-15')).lastrowid
    c.execute("UPDATE document SET current_version=?,approved_version=?,status='approved' WHERE id=?",(vid,vid,doc['id']));c.commit()
    class Relay:
        def call(self,action,payload,operation_id):
            if action=='preview':return {'state':'confirmed','fingerprint':'v1'}
            assert action=='sign' and payload['signatory_id']==uid and payload['actor_id']==uid
            return {'operation_id':operation_id,'state':'confirmed','source_fingerprint':'v1','signatory_id':uid,
                    'url':'https://drive.google.com/file/d/signedfile12345/view','fingerprint':'signed-v1'}
    monkeypatch.setattr(ops,'get_adapter',lambda:Relay())
    client=TestClient(app_mod.app);client.cookies.set(auth.COOKIE_NAME,session_token(user))
    try:
        page=client.get('/documents/'+str(doc['id']));csrf=token(page)
        preview=client.post(f"/documents/{doc['id']}/sign_preview",data={'csrf':csrf,'revision':1})
        assert preview.status_code==200,preview.text
        assert 'Review your signature placement' in preview.text and '/me/signature.png' in preview.text
        result=client.post(f"/documents/{doc['id']}/sign",data={'csrf':csrf,'revision':1,'confirmed_fingerprint':'v1'},follow_redirects=False)
        assert result.status_code==303,result.text
        assert d.raw(c,doc['id'])['status']=='ready_to_release'
    finally:
        st.set_setting(c,'documents.enabled',old);c.close();client.close()
