"""Directory hints are escaped, visibly reviewable, and never trigger a merge."""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


SOURCE = Path(__file__).resolve().parents[1] / 'templates/cleanup.html'
SCRIPT = SOURCE.read_text().split('<script>\n(function () {', 1)[1].split('</script>', 1)[0]


def test_directory_hint_is_safe_and_separate_from_merge():
    options = {'executable_path': os.environ['CSS_TEST_CHROMIUM']} if os.environ.get('CSS_TEST_CHROMIUM') else {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content('''<input id="q"><div id="list"><div class="row" data-f="pending" data-name="example">
          <button class="ai-ask" data-a="1" data-b="2">Ask AI</button>
          <form action="/directory/cleanup/merge"><button type="submit">fold in</button></form>
          <div id="ai-hint-1-2"></div></div></div><div id="empty"></div>''')
        page.evaluate('''() => {
          window.__calls = [];
          window.fetch = url => { window.__calls.push(url); return Promise.resolve({json: async () => ({
            ok:true, relation:'same', reason:'<img src=x onerror="window.__unsafe=1">',
            interaction_id:7, review_required:true
          })}); };
        }''')
        page.add_script_tag(content='(function () {' + SCRIPT)
        page.locator('.ai-ask').click()
        expect(page.locator('#ai-hint-1-2')).to_contain_text('review both records before merging')
        expect(page.locator('#ai-hint-1-2')).to_contain_text('<img src=x onerror=')
        assert page.locator('#ai-hint-1-2 img').count() == 0
        assert page.evaluate('window.__unsafe') is None
        assert page.evaluate('window.__calls') == ['/directory/cleanup/ai-suggest']
        expect(page.locator('form[action="/directory/cleanup/merge"] button')).to_be_visible()
        browser.close()
