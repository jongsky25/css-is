import re
import storage as st
import documents as d


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
        created=viewer.post('/documents/new',data={'csrf':csrf,'subject':'Hidden document','type':'memo'},follow_redirects=False)
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
    client=TestClient(app_mod.app);client.cookies.set(auth.COOKIE_NAME,auth.make_token(user))
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
