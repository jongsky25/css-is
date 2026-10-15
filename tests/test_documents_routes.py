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
