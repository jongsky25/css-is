"""Chromium proves that model-authored summary text is rendered as text."""
from pathlib import Path
import os

from playwright.sync_api import sync_playwright, expect

SCRIPT = Path(__file__).resolve().parents[1] / 'static/js/activity_ai.js'


def test_summary_escapes_model_text_and_does_not_submit_any_form():
    options = {'executable_path': os.environ['CSS_TEST_CHROMIUM']} if os.environ.get('CSS_TEST_CHROMIUM') else {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        context = browser.new_context()
        page = context.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content('''<button type="button" id="aiSummaryBtn" data-event="1">AI summary</button>
          <span id="aiSummaryStatus" hidden>Summarizing</span><div id="aiSummaryResult"></div>''')
        page.evaluate('''() => {
          window.__calls = 0;
          window.fetch = () => {
            window.__calls++;
            return Promise.resolve({ok:true,json:() => Promise.resolve({ok:true,
              bullets:['<img src=x onerror="window.__verbatim_pwned=1">']})});
          };
        }''')
        page.add_script_tag(content=SCRIPT.read_text())
        page.locator('#aiSummaryBtn').click()
        expect(page.locator('#aiSummaryResult li')).to_contain_text('<img src=x onerror=')
        assert page.locator('#aiSummaryResult img').count() == 0
        assert page.evaluate('window.__verbatim_pwned') is None
        assert page.evaluate('window.__calls') == 1
        context.close()
        browser.close()
