"""Inbox name search uses the complete permitted queue, before pagination."""
import pytest
import documents as docs
import documents_intake as intake
from tests.test_documents import registry
from tests.test_documents_intake import seed
from tests.test_document_intake_friction import intake_http
from tests.test_document_guidance_browser import browser
from tests.test_documents_email import setup, signed
from tests.test_documents_email_queue import enable


def test_search_before_pagination_counts_and_literal_characters(registry):
    conn,users,_,_=registry
    seed(registry,65)
    conn.execute("UPDATE document_intake SET original_name='Target 100%_memo.pdf' WHERE id>30")
    conn.execute("UPDATE document_intake SET state='attention' WHERE id=65")
    conn.execute("UPDATE document_intake SET claimed_by=?,claim_until='2099-01-01' WHERE id=64",(users[1]['id'],))
    conn.commit()
    page,more,counts=intake.list_page(conn,users[1],query=' tArGeT ')
    assert len(page)==30 and more and page[0]['id']==31
    assert counts=={'waiting':34,'attention':1}
    assert len(intake.list_page(conn,users[1],page=2,query='Target')[0])==4
    assert intake.review_counts(conn,users[1],query='Target')=={'all':34,'ready':33,'mine':1,'others':0}
    assert len(intake.list_page(conn,users[1],review='mine',query='%_')[0])==1
    assert intake.list_page(conn,users[1],query="' OR 1=1 --")[0]==[]
    assert intake.list_page(conn,users[1],query='No such file')[2]=={}
    assert len(intake.queue_query(' x'*200))==120
    assert conn.execute('SELECT MAX(revision) FROM document_intake').fetchone()[0]==1


def test_search_does_not_disclose_restricted_or_secondary_entries(registry):
    conn,users,_,_=registry
    seed(registry,2)
    doc=docs.register(conn,users[0],{'subject':'Private','direction':'OUT','type':'memo'})
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],))
    conn.execute('UPDATE document_intake SET document_id=? WHERE id=1',(doc['id'],))
    conn.execute('UPDATE document_intake SET email_primary=0 WHERE id=2')
    conn.commit()
    assert intake.list_page(conn,users[1],query='scan')[0]==[]
    assert intake.list_page(conn,users[1],query='scan')[2]=={}
    assert intake.review_counts(conn,users[1],query='scan')=={'all':0,'ready':0,'mine':0,'others':0}


def test_email_subject_search_counts_message_once(setup):
    conn,_,uid,client=setup
    enable(conn,uid)
    assert signed(client).status_code==201
    conn.execute("UPDATE document_intake SET original_name='attachment.pdf'")
    conn.execute("UPDATE document_intake_email SET subject='Budget & planning review'")
    conn.commit()
    page,more,counts=intake.list_page(conn,{'id':uid},query='PLANNING')
    assert len(page)==1 and not more and counts=={'waiting':1}
    assert page[0]['email_subject']=='Budget & planning review'
    assert intake.review_counts(conn,{'id':uid},query='planning')['all']==1


@pytest.mark.parametrize('scripts',[True,False])
def test_search_filter_return_and_clear_on_phone(browser,intake_http,admin,scripts):
    from urllib.parse import urlsplit,parse_qs
    conn,user,_=intake_http
    context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=scripts)
    page=context.new_page();posts=[]
    def serve(route):
        request=route.request;parts=urlsplit(request.url)
        if parts.hostname!='office.test':route.abort();return
        if request.method=='POST':posts.append(parts.path)
        response=admin.request(request.method,parts.path+('?' + parts.query if parts.query else ''),content=request.post_data_buffer,
            headers={k:v for k,v in request.headers.items() if k.lower()=='content-type'},follow_redirects=request.method=='POST')
        route.fulfill(status=response.status_code,body=response.content,
            headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    try:
        page.goto('http://office.test/documents/intake?review=ready&page=2')
        page.get_by_role('searchbox',name='File name or email subject').fill('Letter 2')
        page.get_by_role('button',name='Search Inbox',exact=True).click()
        assert 'page=' not in page.url and 'review=ready' in page.url
        assert page.locator('tbody tr').count()==1
        assert 'Letter 2.pdf' in page.locator('tbody').inner_text()
        assert not posts
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.get_by_role('button',name='Review',exact=True).click()
        page.get_by_role('link',name='Back to Inbox').click()
        assert parse_qs(urlsplit(page.url).query)['q']==['Letter 2']
        # Claiming moved the item out of Ready; the search persists when changing view.
        assert 'No files match' in page.locator('tbody').inner_text()
        page.get_by_role('link',name='My reviews (1)',exact=True).click()
        assert 'Letter 2.pdf' in page.locator('tbody').inner_text()
        page.get_by_role('link',name='All reviews (1)',exact=True).click()
        page.get_by_role('link',name='Clear search',exact=True).click()
        assert page.locator('tbody tr').count()==2
        assert len(posts)==1
    finally:context.close()


def test_search_escaping_and_server_bound(intake_http,admin):
    response=admin.get('/documents/intake',params={'q':'<script>alert(1)</script>'})
    assert response.status_code==200
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text
    response=admin.get('/documents/intake',params={'q':'x'*300})
    assert response.status_code==200
    assert 'value="'+'x'*120+'"' in response.text
