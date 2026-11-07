"""Inbox availability filters apply before pagination and retain claim authority."""
import pytest
import documents as docs
import documents_intake as intake
import documents_permissions as permissions
import tzutil as tz
from tests.test_documents import registry
from tests.test_documents_intake import seed
from tests.test_document_intake_friction import intake_http


def test_availability_counts_and_filters_before_pagination(registry):
    conn, users, _, _ = registry
    seed(registry, 65)
    conn.execute('UPDATE document_intake SET claimed_by=?,claim_until=? WHERE id<=31', (users[0]['id'],'2099-01-01'))
    conn.execute('UPDATE document_intake SET claimed_by=?,claim_until=? WHERE id=32', (users[1]['id'],'2099-01-01'))
    conn.execute('UPDATE document_intake SET claimed_by=?,claim_until=? WHERE id=33', (users[0]['id'],tz.now_iso()))
    conn.execute('UPDATE document_intake SET claimed_by=?,claim_until=NULL WHERE id=34', (users[0]['id'],))
    conn.commit()
    assert intake.review_counts(conn,users[1]) == {'all':65,'ready':33,'mine':1,'others':31}
    ready,more,_=intake.list_page(conn,users[1],review='ready')
    assert len(ready)==30 and more and ready[0]['id']==33
    assert len(intake.list_page(conn,users[1],page=2,review='ready')[0])==3
    assert [r['id'] for r in intake.list_page(conn,users[1],review='mine')[0]]==[32]
    assert len(intake.list_page(conn,users[1],review='others')[0])==30
    # A list read never claims anything or increments a revision.
    assert conn.execute('SELECT MAX(revision) FROM document_intake').fetchone()[0]==1
    with pytest.raises(docs.Conflict):
        intake.claim(conn,users[1],1,1)
    intake.claim(conn,users[1],33,1)
    assert intake.review_counts(conn,users[1])['mine']==2


def test_counts_share_visibility_primary_and_state_scope(registry):
    conn, users, _, _=registry
    seed(registry,4)
    doc=docs.register(conn,users[0],{'subject':'Private','direction':'OUT','type':'memo','visibility':'restricted'})
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],))
    conn.execute('UPDATE document_intake SET document_id=? WHERE id=1',(doc['id'],))
    conn.execute('UPDATE document_intake SET email_primary=0 WHERE id=2')
    conn.execute("UPDATE document_intake SET state='attention' WHERE id=3")
    conn.commit()
    assert intake.review_counts(conn,users[1])=={'all':1,'ready':1,'mine':0,'others':0}
    assert [r['id'] for r in intake.list_page(conn,users[1],review='ready')[0]]==[4]
    assert intake.review_counts(conn,users[1],'attention')['all']==1
    with pytest.raises(permissions.Denied):
        intake.review_counts(conn,users[4])
    assert intake.review_filter('registered','mine')=='all'
    assert intake.review_filter('waiting',"' OR 1=1")=='all'


def test_filter_claim_and_return_context(intake_http, admin, viewer):
    from html import unescape
    import re
    from urllib.parse import urlsplit,parse_qs
    conn,user,_=intake_http
    page=admin.get('/documents/intake?state=waiting&review=ready')
    assert page.status_code==200
    assert 'Ready to review (2)' in page.text
    action=next(unescape(x) for x in re.findall(r'action="([^"]+)"',page.text) if '/documents/intake/1?' in x)
    csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
    result=admin.post(action,data={'csrf':csrf,'revision':'1','action':'claim'},follow_redirects=False)
    assert result.status_code==303
    origin=parse_qs(urlsplit(result.headers['location']).query)['return_to'][0]
    assert 'review=ready' in origin
    assert 'My reviews (1)' in admin.get('/documents/intake?review=mine').text
    assert viewer.get('/documents/intake?review=ready').status_code==403

from tests.test_document_guidance_browser import browser

@pytest.mark.parametrize('scripts',[True,False])
def test_phone_filter_resume_and_return_without_claiming_on_read(browser,intake_http,admin,scripts):
    from urllib.parse import urlsplit
    conn,user,_=intake_http
    intake.claim(conn,user,1,1)
    context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=scripts)
    page=context.new_page()
    posts=[]
    def serve(route):
        request=route.request; parts=urlsplit(request.url)
        if parts.hostname!='office.test':
            route.abort();return
        if request.method=='POST':posts.append(parts.path)
        response=admin.request(request.method,parts.path+('?' + parts.query if parts.query else ''),
            content=request.post_data_buffer,headers={k:v for k,v in request.headers.items() if k.lower()=='content-type'},follow_redirects=request.method=='POST')
        route.fulfill(status=response.status_code,body=response.content,
            headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    try:
        page.goto('http://office.test/documents/intake')
        page.get_by_role('link',name='My reviews (1)',exact=True).click()
        assert page.locator('tbody tr').count()==1
        assert not posts
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.get_by_role('button',name='Resume review',exact=True).click()
        page.wait_for_load_state()
        assert page.locator('.doc-queue-return').count(), (page.url, page.locator('body').inner_text()[:1600], posts)
        page.get_by_role('link',name='Back to Inbox').click()
        assert 'review=mine' in page.url
        assert len(posts)==1
        page.get_by_role('link',name='Ready to review (1)',exact=True).click()
        assert 'Letter 2.pdf' in page.locator('tbody').inner_text()
        assert 'Letter 1.pdf' not in page.locator('tbody').inner_text()
    finally:context.close()
