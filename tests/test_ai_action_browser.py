"""The landing assistant displays action details before any real submission."""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


SCRIPT = (Path(__file__).resolve().parents[1] / 'static/js/assistant.js').read_text()


def test_action_requires_explicit_confirmation_and_escapes_description():
    options = {'executable_path': os.environ['CSS_TEST_CHROMIUM']} if os.environ.get('CSS_TEST_CHROMIUM') else {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content('<div id="result"></div>')
        page.evaluate('''() => {
          window.__submits = [];
          HTMLFormElement.prototype.submit = function () {
            window.__submits.push({action:this.getAttribute('action'),
              fields:Array.from(this.elements).map(el => [el.name,el.value])});
          };
          window.fetch = () => Promise.resolve({ok:true,json:async () => ({
            kind:'action',action:'create_activity_draft',method:'POST',url:'/create',
            description:'Start <img src=x onerror="window.__unsafe=1">',
            fields:{activity_name:'Review Workshop',event_date:'2026-10-25',event_type:'bureau'},
            interaction_id:7
          })});
        }''')
        page.add_script_tag(content=SCRIPT)
        page.evaluate("CSSAssistant.ask('start a draft', document.getElementById('result'), {autoNavigate:false})")
        expect(page.locator('#startConfirm')).to_be_visible()
        expect(page.locator('#result')).to_contain_text('<img src=x onerror=')
        assert page.locator('#result img').count() == 0
        assert page.evaluate('window.__unsafe') is None
        assert page.evaluate('window.__submits') == []
        page.locator('#startCancel').click()
        assert page.evaluate('window.__submits') == []
        page.evaluate("CSSAssistant.ask('start a draft', document.getElementById('result'), {autoNavigate:false})")
        page.locator('#startConfirm').click()
        assert page.evaluate('window.__submits') == [{'action':'/create','fields':[
            ['activity_name','Review Workshop'],['event_date','2026-10-25'],['event_type','bureau']]}]
        browser.close()
