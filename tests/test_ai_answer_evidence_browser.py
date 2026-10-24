"""The assistant shows verified survey sources without treating labels as markup."""
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


SCRIPT = (Path(__file__).resolve().parents[1] / 'static/js/assistant.js').read_text()


def test_verified_answer_shows_sources_and_fixed_answer_does_not():
    options = {'executable_path': os.environ['CSS_TEST_CHROMIUM']} if os.environ.get('CSS_TEST_CHROMIUM') else {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content('<div id="result"></div>')
        page.evaluate('''() => {
          window.__reply = {
            kind:'answer', served_by:'verified_facts', interaction_id:7,
            text:'Activity satisfaction: not enough valid ratings. As of 2026-10-24.',
            sources:[
              {id:'activity.42.satisfaction', label:'Workshop <img src=x onerror="window.__unsafe=1">',
               valid_ratings:0, as_of:'2026-10-24'},
              {id:'survey.2.satisfaction', label:'Activity survey satisfaction',
               valid_ratings:3, as_of:'2026-10-24'}]
          };
          window.fetch = () => Promise.resolve({ok:true, json:async () => window.__reply});
        }''')
        page.add_script_tag(content=SCRIPT)
        page.evaluate("CSSAssistant.ask('show survey facts', document.getElementById('result'))")
        details = page.locator('#result details.start-evidence')
        expect(details).to_have_count(1)
        expect(details.locator('summary')).to_have_text('View survey sources (2)')
        details.locator('summary').click()
        expect(details.locator('li')).to_have_count(2)
        expect(details.locator('li').first).to_contain_text('No valid ratings')
        expect(details.locator('li').last).to_contain_text('3 valid ratings')
        expect(details).to_contain_text('As of 2026-10-24')
        expect(details).to_contain_text('Source activity.42.satisfaction')
        expect(details).to_contain_text('AI selected the topics')
        assert page.locator('#result img').count() == 0
        assert page.evaluate('window.__unsafe') is None

        page.evaluate('''() => {
          window.__reply = {kind:'answer', text:'Your own calendar is clear.', interaction_id:8,
            sources:[{id:'forged',label:'This is not a verified-facts answer'}]};
          CSSAssistant.ask('show my calendar', document.getElementById('result'));
        }''')
        expect(page.locator('#result .start-card-msg')).to_have_text('Your own calendar is clear.')
        expect(page.locator('#result details.start-evidence')).to_have_count(0)
        browser.close()
