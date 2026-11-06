from urllib.parse import urlsplit
import documents as docs
import documents_understanding as understanding
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_registration_browser import browser
from test_documents_understanding import reviewed


def revise_record(conn,user,doc,**changes):
    current=docs.get(conn,user,doc['id'])
    understanding.revise(conn,user,doc['id'],current['revision'],{
        **reviewed(),**changes,'reason':'Checked revised source','review_confirmed':'yes'})


def test_comparison_escapes_source_and_does_not_acknowledge_changes(proposal_record,viewer,admin):
    conn,user,doc,unit,url=proposal_record
    data=payload(viewer.get(url),doc,unit)
    viewer.post(url,data=data)
    revise_record(conn,user,doc,need_0_output='<script>untrusted</script>',focus_evidence='Changed focus evidence')
    revision=docs.get(conn,user,doc['id'])['revision']
    page=viewer.get(url)
    assert page.status_code==200 and page.headers['cache-control']=='no-store'
    assert '2 source fields changed' in page.text
    assert '&lt;script&gt;untrusted&lt;/script&gt;' in page.text
    assert '<script>untrusted</script>' not in page.text
    assert 'Current contribution' in page.text and 'Comments matrix' in page.text
    assert docs.get(conn,user,doc['id'])['revision']==revision
    assert admin.get(url).status_code==404


def test_phone_comparison_without_scripts(proposal_record,viewer,browser):
    conn,user,doc,unit,url=proposal_record
    viewer.post(url,data=payload(viewer.get(url),doc,unit))
    revise_record(conn,user,doc,need_0_output='New deliverable',need_0_evidence='x'*1000)
    context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
    page=context.new_page()
    def serve(route):
        parsed=urlsplit(route.request.url)
        if parsed.hostname!='office.test': route.abort();return
        response=viewer.get(parsed.path,follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    page.goto('http://office.test'+url)
    section=page.locator('#request-comparison')
    assert section.get_by_text('Expected output — Source changed',exact=True).is_visible()
    assert section.get_by_text('New deliverable',exact=True).is_visible()
    assert section.get_by_text('Comments matrix',exact=True).count()==2
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    section.locator('summary').click()
    assert section.get_by_text('Primary focus — Source unchanged',exact=True).is_visible()
    page.screenshot(path='/tmp/request-comparison-phone.png',full_page=True)
    context.close()
