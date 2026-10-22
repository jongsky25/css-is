"""Native report filters retain scope until Apply, with usable recovery on mobile."""
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from tests.test_document_guidance_browser import browser
from tests.test_report_scope_clarity import rp_scope


@pytest.mark.parametrize('width,theme,javascript', [(390, 'light', True), (390, 'dark', True),
                                                  (1440, 'light', True), (1440, 'dark', False)])
def test_filters_apply_deliberately_and_reset_with_or_without_javascript(browser, manager, app_mod, rp_scope, width, theme, javascript):
    conn = app_mod.get_conn()
    all_count = app_mod._report_scope_atoms(app_mod.get_atoms(conn), '', 'all', 3)['response_id'].nunique()
    conn.close()
    member = rp_scope[1]
    context = browser.new_context(viewport={'width': width, 'height': 900},
                                  color_scheme=theme, java_script_enabled=javascript,
                                  reduced_motion='reduce', service_workers='block')
    page = context.new_page()
    errors = []
    posts = []
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    def serve(route):
        req = route.request
        parts = urlsplit(req.url)
        if parts.hostname != 'office.test':
            route.abort(); return
        if req.method != 'GET':
            posts.append(req.url); route.abort(); return
        response = manager.get(parts.path + ('?' + parts.query if parts.query else ''), follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content,
                      headers={k: v for k, v in response.headers.items()
                               if k.lower() not in ('content-length', 'content-encoding', 'set-cookie')})
    page.route('**/*', serve)
    try:
        page.goto(f'http://office.test/reports?type=3&activity={member}')
        expect(page.locator('#report-context')).to_contain_text('3 total submission(s)')
        page.locator('#period').select_option('quarter:2026-Q2')
        # Choosing a filter does not unexpectedly navigate away from the control.
        assert parse_qs(urlsplit(page.url).query) == {'type': ['3'], 'activity': [str(member)]}
        expect(page.locator('#report-context')).to_contain_text('3 total submission(s)')
        apply = page.get_by_role('button', name='Apply filters', exact=True)
        apply.focus(); apply.press('Enter')
        expect(page.locator('#report-context')).to_contain_text('3 total submission(s)')
        expect(page.locator('#report-context')).to_contain_text('2026-04-01 to 2026-06-30')
        assert parse_qs(urlsplit(page.url).query)['period'] == ['quarter:2026-Q2']
        page.locator('details.dl > summary').focus()
        page.locator('details.dl > summary').press('Enter')
        download = page.get_by_role('link', name='Excel (.xlsx) — the numbers', exact=True)
        expect(download).to_be_visible()
        assert parse_qs(urlsplit(download.get_attribute('href')).query)['period'] == ['quarter:2026-Q2']
        def capture(state):
            axe_path = os.environ.get('A18_REPORT_AXE_PATH')
            evidence = os.environ.get('A18_REPORT_EVIDENCE')
            if not javascript or not axe_path or not evidence:
                return
            page.add_script_tag(path=axe_path)
            result = page.evaluate("""async () => {
                const r = await axe.run({include: ['#report-context', '#filterForm', '.dl']},
                    {runOnly:{type:'tag', values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
                return {version:r.testEngine.version, violations:r.violations,
                    incomplete:r.incomplete.map(x=>({id:x.id,impact:x.impact})), passes:r.passes.length};
            }""")
            result.update(width=width, theme=theme, state=state,
                overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            out = Path(evidence); out.mkdir(parents=True, exist_ok=True)
            (out / f'{width}-{theme}-{state}.json').write_text(json.dumps(result, indent=2)+'\n')
            assert not result['violations']
            if width == 390 and theme == 'light' and state == 'filtered':
                page.screenshot(path=str(out / 'report-mobile.png'), full_page=True)
        capture('filtered')
        notes = page.locator('#report-context details > summary')
        notes.focus(); notes.press('Enter')
        expect(page.locator('#report-context details')).to_have_attribute('open', '')
        capture('counts-open')
        notes.press('Enter')
        if javascript:
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,w:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right})).slice(0,20)")
        page.goto('http://office.test/reports?type=3&period=year:2040&activity=99999999')
        expect(page.locator('#report-context')).to_contain_text('No submissions match these filters.')
        expect(page.locator('#period')).to_have_value('year:2040')
        capture('empty')
        if javascript:
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,w:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right})).slice(0,20)")
        page.get_by_role('link', name='Reset report filters', exact=True).click()
        expect(page.locator('#report-context')).to_contain_text(f'{all_count} total submission(s)')
        expect(page.locator('#period')).to_have_value('all')
        if javascript:
            trigger = page.locator('.combobox-trigger')
            expect(trigger).to_have_accessible_name(re.compile(r'Activity .*All activities'))
            trigger.click()
            search = page.get_by_role('textbox', name='Search activities…', exact=True)
            search.fill('Scope Bravo')
            search.press('ArrowDown'); search.press('Enter')
            expect(trigger).to_have_accessible_name(re.compile(r'Activity .*Scope Bravo'))
        assert not errors and not posts
    finally:
        context.close()
