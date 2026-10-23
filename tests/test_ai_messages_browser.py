"""An AI suggestion waits for review and preserves edits made during the request."""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


SOURCE = Path(__file__).resolve().parents[1] / 'templates/activity_manage.html'
SCRIPT = SOURCE.read_text().split('<script>\n    (function () {', 1)[1].split('</script>', 1)[0]
HTML = '''<script id="msgDrafts" type="application/json">{"welcome":{"personal":"Static draft"}}</script>
<form id="msgForm" action="/activities/token/messages">
  <div class="tones" data-slot="welcome" data-target="welcomeMsg">
    <button type="button" class="tone" data-tone="personal">Personal</button>
    <button type="button" class="tone ai-draft" data-slot="welcome" data-target="welcomeMsg">AI</button>
  </div>
  <span class="ai-note" data-slot="welcome" hidden></span>
  <textarea id="welcomeMsg" name="welcome_message">Human draft</textarea>
  <textarea id="endingMsg" name="ending_message"></textarea>
  <span id="msgStatus"></span>
</form>'''


def test_ai_message_requires_review_and_keeps_concurrent_edits():
    options = {'executable_path': os.environ['CSS_TEST_CHROMIUM']} if os.environ.get('CSS_TEST_CHROMIUM') else {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content(HTML)
        page.evaluate('''() => {
          window.__calls = []; window.__confirm = false;
          window.confirm = () => window.__confirm;
          window.fetch = (url) => { window.__calls.push(url);
            if (url.endsWith('/ai-draft')) return new Promise(resolve => { window.__finish = () => resolve({json: async () =>
              ({ok:true,text:'Hello {name}! Welcome to Immunization Forum.',review_required:true})}); });
            return Promise.resolve({ok:true});
          };
        }''')
        page.add_script_tag(content='(function () {' + SCRIPT)
        button = page.locator('.ai-draft')
        message = page.locator('#welcomeMsg')

        button.click()
        page.evaluate('window.__finish()')
        expect(page.locator('.ai-note')).to_contain_text('not applied')
        expect(message).to_have_value('Human draft')
        assert page.evaluate('window.__calls.filter(x => !x.endsWith("/ai-draft")).length') == 0

        button.click()
        message.fill('New human edit')
        page.evaluate('window.__finish()')
        expect(page.locator('.ai-note')).to_contain_text('Your edits were kept')
        expect(message).to_have_value('New human edit')

        page.evaluate('window.__confirm = true')
        button.click()
        page.evaluate('window.__finish()')
        expect(message).to_have_value('Hello {name}! Welcome to Immunization Forum.')
        browser.close()
