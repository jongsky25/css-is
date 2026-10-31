"""Responsive layout and read-only email review against a rendered calendar entry."""
import pytest
from playwright.sync_api import expect

from tests.test_calendar_entry_pages import conn, create, uid  # noqa: F401
from tests.test_document_guidance_browser import browser  # noqa: F401
# Reuse the local HTTP adapter and shared browser (actual TestClient requests; external hosts blocked).
from tests.test_rooms_guidance_browser import room_page as calendar_page, room_writes as writes


@pytest.mark.parametrize('width,theme', [(360, 'light'), (390, 'dark'), (768, 'light'), (1280, 'light'), (1440, 'dark'), (1440, 'contrast')])
def test_workspace_resizes_and_notice_requires_review(calendar_page, viewer, width, theme):
    page, state, c, context = calendar_page
    eid = create(viewer, title='Quarterly planning meeting', kind='meeting', venue='Conference room A',
                 start_time='09:00', end_time='11:00', people=[str(uid(c, 'viewer@test.local'))])
    sent = []

    def capture_send(route):
        # Only the final send is answered here; it must not deliver a real notice.
        sent.append(route.request.post_data)
        route.fulfill(status=200, body='Notice submitted')

    page.route('**/notice/send', capture_send)
    page.set_viewport_size({'width': width, 'height': 1000})
    page.goto('/calendar')
    page.evaluate('(theme) => localStorage.setItem("theme", theme)', theme)
    page.goto(f'/calendar/entries/{eid}')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, theme)
    assert not page.locator('.cal-outside-fields').is_visible()
    page.locator('input[value=outside]').check()
    assert page.locator('.cal-outside-fields').is_visible()
    page.locator('input[value=blhsd]').check()
    main = page.locator('.cal-work-main').bounding_box()
    side = page.locator('.cal-context').bounding_box()
    assert (side['x'] > main['x'] + main['width']) if width > 1000 else (side['y'] > main['y'])
    agenda = page.locator('#notice-agenda')
    agenda.fill('1. Opening\n2. Updates')
    page.locator('#notice-extra').fill('guest@example.org')
    page.locator('[data-notice-review]').click()
    expect(page.locator('[data-notice-preview]')).to_be_visible()
    expect(page.locator('[data-review-extra]')).to_contain_text('guest@example.org')
    expect(page.locator('[data-review-agenda]')).to_contain_text('2. Updates')
    assert not sent and not writes(state)
    page.locator('[data-notice-edit]').click()
    expect(page.locator('[data-notice-preview]')).not_to_be_visible()
    expect(agenda).to_have_value('1. Opening\n2. Updates')
    page.locator('#notice-extra').fill('invalid')
    page.locator('[data-notice-review]').click()
    expect(page.locator('[data-notice-preview]')).not_to_be_visible()
    page.locator('#notice-extra').fill('guest@example.org')
    page.locator('[data-notice-review]').click()
    # Changes invalidate an existing review even if fields are edited by keyboard.
    agenda.fill('Updated agenda')
    expect(page.locator('[data-notice-preview]')).not_to_be_visible()
    page.locator('[data-notice-review]').click()
    if width == 1440 and theme == 'contrast':
        with page.expect_request('**/notice/send'):
            page.locator('[data-notice-send]').click()
        assert len(sent) == 1 and 'agenda=Updated+agenda' in sent[0]
    assert not writes(state)
