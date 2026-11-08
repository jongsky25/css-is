"""Read-only source round trips and existing contribution action context."""
import html
import re
from urllib.parse import urlencode, urlsplit
import pytest
import documents_navigation as nav
import documents_request_work as proposals
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_registration_browser import browser
from test_document_request_comparison_routes import revise_record
from test_documents_routes import token

ORIGIN = '/documents/actions?view=mine&step_state=waiting&overdue=1#document-step-1-workflow'


def prepare(record, viewer):
    c,u,doc,unit,url=record
    assert viewer.post(url,data=payload(viewer.get(url),doc,unit),follow_redirects=False).status_code==303
    saved=proposals.existing(c,u,doc['id'],0)
    return saved,nav.request_work_url(saved,ORIGIN)


def test_round_trip_changed_source_and_read_only(proposal_record,viewer,admin):
    c,u,doc,unit,url=proposal_record
    saved,target=prepare(proposal_record,viewer)
    revise_record(c,u,doc,need_0_output='Changed deliverable')
    before={t:c.execute('SELECT * FROM '+t).fetchall() for t in ('work_task','work_case','work_event','document_request_work','document')}
    receipt=viewer.get(nav.record_url(url,ORIGIN))
    assert html.escape(target,quote=True) in receipt.text
    page=viewer.get(target)
    assert page.status_code==200
    assert 'Back to reviewed request and comparison' in page.text
    assert html.escape(nav.record_url(url,ORIGIN),quote=True) in page.text
    assert 'The saved request changed.' in page.text
    assert html.escape(ORIGIN,quote=True) in page.text
    for t,rows in before.items(): assert c.execute('SELECT * FROM '+t).fetchall()==rows
    assert admin.get(target).status_code==404


@pytest.mark.parametrize('source',['-1','99999999','1'*30,'١','bad'])
def test_forged_source_cannot_create_return_link(proposal_record,viewer,source):
    saved,_=prepare(proposal_record,viewer)
    page=viewer.get(f"/work/{saved['case_id']}?"+urlencode({'source_task':source,'return_to':ORIGIN}))
    assert page.status_code==200
    assert 'aria-label="Request context"' not in page.text


@pytest.mark.parametrize('origin',['https://evil.test/','//evil.test','/work/1','/documents/actions?view=mine%0aevil'])
def test_unsafe_queue_discarded(proposal_record,viewer,origin):
    saved,_=prepare(proposal_record,viewer)
    page=viewer.get(f"/work/{saved['case_id']}?"+urlencode({'source_task':saved['task_id'],'return_to':origin}))
    assert 'Back to reviewed request and comparison' in page.text
    assert 'Back to Documents queue' not in page.text
    assert 'evil.test' not in page.text


def test_existing_action_validation_and_save_keep_source_context(proposal_record,viewer):
    c,u,doc,unit,url=proposal_record
    saved,target=prepare(proposal_record,viewer)
    c.execute('UPDATE work_case SET lead_id=? WHERE id=?',(u['id'],saved['case_id']));c.commit()
    page=viewer.get(target)
    action=html.unescape(re.search(r'action="([^"]+/milestone[^\"]*)"',page.text)[1])
    revision=c.execute('SELECT revision FROM work_task WHERE id=?',(saved['task_id'],)).fetchone()[0]
    data={'csrf':token(page),'revision':str(revision),'due_date':'2026-11-19','reason':'Updated target'}
    invalid=viewer.post(action,data={**data,'revision':'0'},follow_redirects=False)
    assert invalid.status_code==409 and 'Back to reviewed request and comparison' in invalid.text
    response=viewer.post(action,data=data,follow_redirects=False)
    assert response.status_code==303
    assert response.headers['location']==target
    assert 'Back to reviewed request and comparison' in viewer.get(response.headers['location']).text


@pytest.mark.parametrize('width',[390,1280])
@pytest.mark.parametrize('scripts',[False,True])
def test_native_keyboard_phone_round_trip(proposal_record,viewer,browser,scripts,width):
    saved,target=prepare(proposal_record,viewer)
    start=nav.record_url(proposal_record[-1],ORIGIN)
    context=browser.new_context(viewport={'width':width,'height':844},java_script_enabled=scripts)
    page=context.new_page();writes=[]
    def serve(route):
        parsed=urlsplit(route.request.url)
        if parsed.hostname!='office.test':route.abort();return
        if route.request.method!='GET':writes.append(parsed.path);route.abort();return
        response=viewer.get(parsed.path+('?' + parsed.query if parsed.query else ''),follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    try:
        page.goto('http://office.test'+start)
        link=page.get_by_role('link',name='Open the work item and contribution');link.focus();link.press('Enter')
        page.wait_for_url('http://office.test'+target)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=f'/tmp/request-work-navigation-{scripts}-{width}.png',full_page=True)
        back=page.get_by_role('link',name='Back to reviewed request and comparison');back.focus();back.press('Enter')
        page.wait_for_url('http://office.test'+start)
        assert page.locator('#request-comparison').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not writes
    finally:context.close()


def test_source_from_another_case_is_not_used(proposal_record,viewer):
    import work
    c,u,doc,unit,url=proposal_record
    saved,_=prepare(proposal_record,viewer)
    other=work.create(c,u,{'title':'Separate work','outcome':'Separate output','unit_id':str(unit)})
    page=viewer.get(f"/work/{other['id']}?"+urlencode({'source_task':saved['task_id'],'return_to':ORIGIN}))
    assert page.status_code==200
    assert 'aria-label="Request context"' not in page.text
    assert url not in page.text
