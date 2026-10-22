"""From action cards to focused current forms, with no automatic mutations."""
from urllib.parse import urlsplit

import pytest

from tests.test_document_guidance_browser import browser
from tests.test_document_guidance_routes import detail_record
from tests.test_document_action_routes import review_ready


@pytest.mark.parametrize('step,width,theme',[('draft',390,'light'),('contribution',1280,'dark'),('stale_review',390,'light')])
def test_action_card_opens_the_right_current_control(browser,detail_record,viewer,step,width,theme):
    c,user,doc,url=detail_record
    if step=='stale_review':doc,rp=review_ready(c,user,doc)
    context=browser.new_context(viewport={'width':width,'height':850},color_scheme=theme)
    page=context.new_page();posts=[];errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def serve(route):
        request=route.request;parts=urlsplit(request.url)
        if parts.hostname!='office.test':route.abort();return
        if request.method!='GET':posts.append(request.url);route.abort();return
        response=viewer.get(parts.path+('?' + parts.query if parts.query else ''),follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,
            headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    try:
        page.goto('http://office.test/documents/actions')
        card=page.locator('.doc-action-card').last
        assert card.evaluate('element => element.scrollWidth <= element.clientWidth')
        if step=='contribution':
            aid=c.execute('SELECT id FROM document_assignment WHERE document_id=?',(doc['id'],)).fetchone()[0]
            selector='#document-contribution-'+str(aid)
            link=page.get_by_role('link',name='Update contribution',exact=True)
        else:
            selector='#document-action-review' if step=='stale_review' else '#document-action-attach'
            link=page.get_by_role('link',name='Review this exact version' if step=='stale_review' else 'Attach the draft',exact=True)
        if step=='stale_review':
            c.execute("UPDATE resource_person SET position='Staff' WHERE id=?",(rp,));c.commit()
        link.focus();link.press('Enter')
        page.wait_for_url('**/documents/*#*')
        if step=='stale_review':
            assert page.locator(selector).count()==0
            assert page.locator('#document-next').get_attribute('data-stage')=='review_authority'
        else:
            page.wait_for_function("selector => document.activeElement === document.querySelector(selector + ' > summary')",arg=selector)
            assert page.locator(selector).evaluate('element => element.open && element.closest(".doc-secondary").open')
        assert not posts and not errors
        assert c.execute('SELECT revision FROM document WHERE id=?',(doc['id'],)).fetchone()[0]==doc['revision']
    finally:context.close()
