import re
from urllib.parse import urlsplit
import pytest
import storage as st
from test_document_understanding_review_routes import review_record
from test_document_registration_browser import browser
from test_documents_routes import token


@pytest.fixture
def proposal_record(review_record):
    c,u,doc,_=review_record
    st.set_setting(c,'work.enabled','1')
    unit=st.add_org_unit(c,'Proposal unit','division','PROP')
    return c,u,doc,unit,f"/documents/{doc['id']}/requests/0/work"


def payload(page,doc,unit):
    return {'csrf':token(page),'revision':str(doc['revision']),
            'source_hash':re.search(r'name="source_hash" value="([^"]+)"',page.text)[1],
            'title':'Submit comments','expected_output':'Comments matrix','unit_id':str(unit),
            'due_date':'2026-11-20','confirmed':'yes'}


def test_routes_confirm_retry_access_and_invalid_fields(proposal_record,viewer,admin):
    c,u,doc,unit,url=proposal_record
    page=viewer.get(url)
    assert page.status_code==200 and page.headers['cache-control']=='no-store'
    data=payload(page,doc,unit)
    assert admin.get(url).status_code==404
    assert viewer.post(url,data={**data,'csrf':''}).status_code==403
    for key in ('revision','unit_id','expected_output'):
        assert viewer.post(url,json={**data,key:{}}).status_code==400
    assert viewer.post(url,data={**data,'confirmed':''}).status_code==400
    response=viewer.post(url,data=data,follow_redirects=False)
    assert response.status_code==303
    receipt=viewer.get(url)
    assert 'Work was proposed' in receipt.text and 'Source preserved' in receipt.text
    assert 'Create proposed work' not in receipt.text
    case_id=c.execute('SELECT case_id FROM document_request_work').fetchone()[0]
    assert 'Reviewed request and preserved source' in viewer.get(f'/work/{case_id}').text
    assert viewer.post(url,data=data,follow_redirects=False).status_code==303
    assert viewer.post(url,data={**data,'title':'Changed proposal'}).status_code==409
    assert c.execute('SELECT COUNT(*) FROM work_case').fetchone()[0]==1
    for index in (-1,5):
        assert viewer.get(url.replace('/0/',f'/{index}/')).status_code==400
        assert viewer.post(url.replace('/0/',f'/{index}/'),data=data).status_code==400


def test_phone_creates_proposal_with_source_and_no_assignment(browser,proposal_record,viewer):
    c,u,doc,unit,url=proposal_record
    context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
    page=context.new_page()
    def serve(route):
        request=route.request
        parsed=urlsplit(request.url)
        if parsed.hostname!='office.test': route.abort();return
        if request.method=='POST':
            response=viewer.post(parsed.path,content=request.post_data,headers={'content-type':request.headers['content-type']},follow_redirects=True)
        else: response=viewer.get(parsed.path,follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    page.goto('http://office.test'+url)
    page.locator('[name=unit_id]').select_option(str(unit))
    page.locator('[name=expected_output]').fill('Reviewed comments matrix')
    page.locator('[name=confirmed]').check()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button',name='Create proposed work',exact=True).click()
    page.get_by_role('status').filter(has_text='Work was proposed').wait_for(state='visible')
    assert page.get_by_text('Source preserved when work was proposed',exact=True).is_visible()
    assert c.execute('SELECT status,owner_id FROM work_task').fetchone()==('proposed',None)
    page.screenshot(path='/tmp/request-work-phone.png',full_page=True)
    context.close()
