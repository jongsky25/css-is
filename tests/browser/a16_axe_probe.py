"""Explicit local axe evidence runner (excluded from ordinary test discovery).

See docs/SHARED_ACCESSIBILITY.md. Uses a separately installed, pinned axe engine;
no runtime dependency, production requests, fixture writes or real staff data.
"""
import hashlib
import json
import os
from pathlib import Path

from tests.test_shared_accessibility import browser, shell_page, component_page, snapshot_page


def test_probe(component_page, snapshot_page):
    page, state, context, ids = component_page
    engine = Path(os.environ['A16_AXE_PATH'])
    results = []

    def scan(name, theme, width):
        page.evaluate('(theme) => document.documentElement.dataset.theme=theme', theme)
        page.add_script_tag(path=str(engine))
        result = page.evaluate('''async () => {
            const r=await axe.run(document,{runOnly:{type:'tag',values:[
                'wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
            return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,
              nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),
              incomplete:r.incomplete.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),
              overflow:document.documentElement.scrollWidth>innerWidth};
        }''')
        result.update(surface=name, width=width, theme=theme)
        results.append(result)

    for theme in ('light', 'dark'):
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 1000 if width > 400 else 844})
            for path in ('/', '/css', '/wellness', '/dashboard', '/r/' + ids['qr_token']):
                page.goto('http://office.test' + path)
                if page.locator('#snapshot-bd:visible').count():
                    page.locator('#snapshot-close').click()
                scan('Survey' if path.startswith('/r/') else path, theme, width)
            page.goto('http://office.test/')
            if width < 900:
                page.locator('.nav-toggle > summary').click()
            else:
                page.locator('.navgroup > summary').first.click()
            scan('Navigation open', theme, width)
            page.keyboard.press('Escape')
            page.goto('http://office.test/')
            page.keyboard.press('Control+k')
            scan('Search open', theme, width)
            page.keyboard.press('Escape')
            page.locator('#sfBtn').focus()
            page.locator('#sfBtn').press('Enter')
            scan('Feedback open', theme, width)
            page.keyboard.press('Escape')
            page.goto('http://office.test/?tour=1')
            scan('Tour open', theme, width)
            page.keyboard.press('Escape')
            page.evaluate("localStorage.removeItem('css_snapshot_999999')")
            page.goto('http://office.test/__a16_snapshot')
            scan('Snapshot open', theme, width)
            page.keyboard.press('Escape')
            page.goto('http://office.test/__a16_components')
            scan('Deck and validation errors', theme, width)
    report = {'axe': '4.14.0', 'engine_sha256': hashlib.sha256(engine.read_bytes()).hexdigest(),
              'browser': context.browser.version, 'checks': results, 'errors': state['errors'],
              'notes': 'Synthetic local fixtures. Incomplete checks need manual review. No screen reader or live production test.'}
    Path(os.environ['A16_REPORT']).write_text(json.dumps(report, indent=2) + '\n')
    failures = [(r['surface'], r['width'], r['theme'],
                 [(v['id'], len(v['nodes'])) for v in r['violations']])
                for r in results if r['violations']]
    assert not failures, failures
    assert not state['errors']
