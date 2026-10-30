"""Responsive layout and read-only email review against a rendered calendar entry."""
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from test_calendar_entry_pages import conn, create, uid  # noqa: F401


def test_workspace_resizes_and_notice_requires_review(viewer, conn):
    from playwright.sync_api import sync_playwright
    executable = shutil.which('chromium')
    eid = create(viewer, title='Quarterly planning meeting', kind='meeting', venue='Conference room A',
                 start_time='09:00', end_time='11:00', people=[str(uid(conn, 'viewer@test.local'))])
    html = viewer.get(f'/calendar/entries/{eid}').text
    posts = []

    def serve(route):
        path = urlsplit(route.request.url).path
        if path.startswith('/static/'):
            file = Path(path.lstrip('/'))
            route.fulfill(path=str(file)) if file.is_file() else route.fulfill(status=404)
        elif route.request.method == 'POST':
            posts.append((path, route.request.post_data))
            route.fulfill(status=200, body='Notice submitted')
        elif path == f'/calendar/entries/{eid}':
            route.fulfill(status=200, content_type='text/html', body=html)
        else:
            route.fulfill(status=204)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=executable, args=['--no-sandbox'])
        for width, theme in [(360, 'light'), (390, 'dark'), (768, 'light'), (1280, 'light'), (1440, 'dark'), (1440, 'contrast')]:
            context = browser.new_context(viewport={'width': width, 'height': 1000})
            context.add_init_script(f"localStorage.setItem('theme', '{theme}'); localStorage.setItem('css_tour_optout', '1');")
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', serve)
            page.goto(f'http://testserver/calendar/entries/{eid}')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, theme)
            assert not page.locator('.cal-outside-fields').is_visible()
            page.locator('input[value=outside]').check()
            assert page.locator('.cal-outside-fields').is_visible()
            page.locator('input[value=blhsd]').check()
            main = page.locator('.cal-work-main').bounding_box()
            side = page.locator('.cal-context').bounding_box()
            assert (side['x'] > main['x'] + main['width']) if width > 1000 else (side['y'] > main['y'])
            out = Path('/tmp/calendar-workspace-previews'); out.mkdir(exist_ok=True)
            page.screenshot(path=str(out / f'{width}-{theme}-initial.png'), full_page=True)
            agenda = page.locator('#notice-agenda')
            agenda.fill('1. Opening\n2. Updates')
            page.locator('#notice-extra').fill('guest@example.org')
            page.locator('[data-notice-review]').click()
            assert page.locator('[data-notice-preview]').is_visible()
            assert 'guest@example.org' in page.locator('[data-review-extra]').inner_text()
            assert '2. Updates' in page.locator('[data-review-agenda]').inner_text()
            assert not posts
            page.locator('[data-notice-edit]').click()
            assert not page.locator('[data-notice-preview]').is_visible()
            assert agenda.input_value() == '1. Opening\n2. Updates'
            page.locator('#notice-extra').fill('invalid')
            page.locator('[data-notice-review]').click()
            assert not page.locator('[data-notice-preview]').is_visible()
            page.locator('#notice-extra').fill('guest@example.org')
            page.locator('[data-notice-review]').click()
            # Changes invalidate an existing review even if fields are edited by keyboard.
            agenda.fill('Updated agenda')
            assert not page.locator('[data-notice-preview]').is_visible()
            page.locator('[data-notice-review]').click()
            assert not errors, errors
            out = Path('/tmp/calendar-workspace-previews'); out.mkdir(exist_ok=True)
            page.screenshot(path=str(out / f'{width}-{theme}.png'), full_page=True)
            if width == 1440 and theme == 'contrast':
                page.locator('[data-notice-send]').click()
                assert len(posts) == 1 and posts[0][0] == f'/calendar/entries/{eid}/notice/send'
                assert 'agenda=Updated+agenda' in posts[0][1]
            context.close()
        browser.close()
