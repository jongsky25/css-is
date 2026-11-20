"""Actual forms/routes, persisted private data and legacy public URL boundaries."""
from html import unescape
import re

import pytest
import storage as st
import advisory_workflow as aw
from tests.conftest import ROLE_USERS
from tests.test_advisory import FORM


@pytest.fixture
def draft_route(manager,db_path,monkeypatch):
    c=st.connect(db_path)
    user=st.get_admin_user(c,ROLE_USERS['section_manager'])
    unit=st.add_org_unit(c,'Advisory test division','division','ADVTEST/D1')
    ev=st.create_event(c,'Advisory route test','2026-12-15',created_by=user['username'])
    st.set_setting(c,'documents.enabled','1');st.set_setting(c,'work.enabled','1');c.commit()
    import mailer, short_links
    monkeypatch.setattr(mailer,'send',lambda *a,**k:pytest.fail('No email may be sent'))
    monkeypatch.setattr(short_links,'share',lambda *a,**k:pytest.fail('No shortening request'))
    yield c,user,unit,ev,f"/activities/{ev['event_token']}/advisory/draft"
    c.close()


def form(page,unit,**kwargs):
    hidden={name:unescape(value) for name,value in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',page.text)}
    return {**FORM,**hidden,'unit_id':str(unit),'audience':'both','external':'test@example.invalid',**kwargs}


def test_form_save_replay_history_and_public_boundaries(draft_route,manager,viewer,admin,client):
    c,user,unit,ev,url=draft_route
    page=manager.get(url)
    assert page.status_code==200
    data=form(page,unit)
    saved=manager.post(url,data=data,follow_redirects=False)
    assert saved.status_code==303
    location=saved.headers['location'];record=aw.for_event(c,ev['id'])
    assert manager.post(url,data=data,follow_redirects=False).headers['location']==location
    page=manager.get(location)
    assert 'Private draft' in page.text and 'Number reserved' in page.text
    assert location in manager.get('/advisories').text
    pdf=f"{location}/revisions/{record['current_revision']}/file.pdf"
    assert manager.get(pdf).content.startswith(b'%PDF-')
    assert manager.get(f"/documents/{record['document_id']}",follow_redirects=False).headers['location']==location
    assert manager.get(f"/activities/{ev['event_token']}/advisory/file.png",follow_redirects=True).status_code==200
    assert client.get(f"/e/{ev['event_token']}/advisory.png").status_code==404
    assert manager.post(f"/activities/{ev['event_token']}/advisory/publish",data={'publish':'1'}).status_code==409
    for unauthorized in (viewer,admin):
        assert unauthorized.get(location).status_code==404
        assert unauthorized.get(location+'/history').status_code==404
        assert unauthorized.get(pdf).status_code==404
        assert location not in unauthorized.get('/advisories').text
    changed=form(page,unit,headline='Updated private headline',summary='Clarify headline')
    assert manager.post(url,data=changed,follow_redirects=False).status_code==303
    stale=manager.post(url,data={**changed,'headline':'Stale unsaved work'},follow_redirects=False)
    assert stale.status_code==409 and 'Stale unsaved work' in stale.text
    assert 'value="1"' in stale.text  # Failed writes never silently rebase their revision.
    history=manager.get(location+'/history')
    assert history.status_code==200 and 'Revision 1' in history.text and 'Revision 2' in history.text
    assert c.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM document_job').fetchone()[0]==0


def test_bad_form_keeps_values_and_disabled_modules_keep_draft_readable(draft_route,manager):
    c,user,unit,ev,url=draft_route
    page=manager.get(url);data=form(page,unit,external='invalid',headline='Keep my work')
    invalid=manager.post(url,data=data,follow_redirects=False)
    assert invalid.status_code==422 and 'Keep my work' in invalid.text and '>invalid</textarea>' in invalid.text
    assert aw.for_event(c,ev['id']) is None
    saved=manager.post(url,data={**data,'external':'a@example.invalid'},follow_redirects=False)
    st.set_setting(c,'work.enabled','0');c.commit()
    assert manager.get(saved.headers['location']).status_code==200
    assert 'fieldset disabled' in manager.get(url).text
    denied=manager.post(url,data=form(manager.get(url),unit,summary='Cannot save'),follow_redirects=False)
    assert denied.status_code==422


def test_existing_public_copy_keeps_exact_bytes_after_private_edit(draft_route,manager,client):
    c,user,unit,ev,url=draft_route
    import activity_advisory as aa
    import activity_advisory_routes as routes
    fields=routes._form_fields(FORM);fields['qr_url']='https://office.test/e/test'
    aa.save(c,st.get_event(c,ev['event_token']),fields,user);aa.set_published(c,ev['id'],True)
    public=f"/e/{ev['event_token']}/advisory.png"
    before=client.get(public).content
    existing=manager.get('/advisories/existing')
    assert 'approval history' in existing.text.lower() and ev['event_token'] in existing.text
    saved=manager.post(url,data=form(manager.get(url),unit,headline='Private changes'),follow_redirects=False)
    assert saved.status_code==303
    assert client.get(public).content==before
    assert ev['event_token'] not in manager.get('/advisories/existing').text
    pdf=manager.get(saved.headers['location'])
    assert 'existing public copy stays unchanged' in pdf.text


def test_rendered_artifacts_fit_bound(draft_route,manager):
    c,user,unit,ev,url=draft_route
    result=manager.post(url,data=form(manager.get(url),unit),follow_redirects=False)
    assert result.status_code==303
    sizes=c.execute('SELECT length(data),format FROM advisory_artifact').fetchall()
    assert {fmt for _,fmt in sizes}=={'png','pdf'}
    assert all(0<size<aw.MAX_ARTIFACT_BYTES for size,_ in sizes)
