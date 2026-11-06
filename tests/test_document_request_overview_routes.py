from urllib.parse import urlsplit
import documents as docs
import documents_understanding as understanding
from test_document_understanding_review_routes import review_record
from test_document_request_work_routes import proposal_record, payload
from test_document_registration_browser import browser


def test_detail_and_review_show_work_even_after_source_is_cleared(proposal_record,viewer,admin):
    conn,user,doc,unit,url=proposal_record
    viewer.post(url,data=payload(viewer.get(url),doc,unit))
    current=docs.get(conn,user,doc['id'])
    understanding.revise(conn,user,doc['id'],current['revision'],{
        'needs_status':'unclear','reason':'Removed request after review','review_confirmed':'yes'})
    for path in (f'/documents/{doc["id"]}',f'/documents/{doc["id"]}/understanding'):
        page=viewer.get(path)
        assert page.status_code==200
        assert 'Cleared from the latest review' in page.text
        assert '0 saved requests' in page.text and '1 work contributions visible' in page.text
        assert 'Source changed — compare with the existing work.' in page.text
        assert f'href="{url}"' in page.text
        assert admin.get(path).status_code==404


def test_phone_overview_links_to_proposal_without_scripts(proposal_record,viewer,browser):
    conn,user,doc,unit,url=proposal_record
    context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
    page=context.new_page()
    def serve(route):
        parsed=urlsplit(route.request.url)
        if parsed.hostname!='office.test': route.abort();return
        response=viewer.get(parsed.path,follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    page.goto('http://office.test/documents/'+str(doc['id']))
    summary=page.locator('#request-overview')
    assert summary.get_by_text('Request follow-up overview',exact=True).is_visible()
    assert '1 saved requests' in summary.inner_text()
    assert 'Requested from' in summary.inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    summary.get_by_role('link',name='Review a work proposal',exact=True).click()
    assert page.locator('[name=expected_output]').input_value()=='Comments matrix'
    context.close()
