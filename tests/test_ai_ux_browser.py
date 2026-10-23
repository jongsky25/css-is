"""UX analysis displays source scope and escapes provider-authored text."""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


SOURCE = Path(__file__).resolve().parents[1] / 'templates/ux_insights.html'
SCRIPT = SOURCE.read_text().rsplit('<script>\n(function () {', 1)[1].split('</script>', 1)[0]


def test_ux_analysis_escapes_model_text_and_shows_sample_scope():
    options = {'executable_path': os.environ['CSS_TEST_CHROMIUM']} if os.environ.get('CSS_TEST_CHROMIUM') else {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content('''<button id="ai-analyze-btn" data-days="30">Analyze now</button>
          <div id="ai-analysis-results"></div>''')
        page.evaluate('''() => {
          window.fetch = () => Promise.resolve({json: () => Promise.resolve({
            ok:true, interaction_id:7, event_count:4, window_days:30, truncated:true,
            text:'<img src=x onerror="window.__ux_pwned=1">'
          })});
        }''')
        page.add_script_tag(content='(function () {' + SCRIPT)
        page.locator('#ai-analyze-btn').click()
        expect(page.locator('.ai-result')).to_contain_text('<img src=x onerror=')
        expect(page.locator('.acard .hint')).to_contain_text('4 recorded event(s) in the last 30 day(s) (recent sample)')
        assert page.locator('.ai-result img').count() == 0
        assert page.evaluate('window.__ux_pwned') is None
        browser.close()
