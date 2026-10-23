"""Real Chromium checks that AI suggestions remain reviewable form prefill."""
import os
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright, expect

import storage as st


@pytest.fixture
def triage_page(admin, db_path):
    conn = st.connect(db_path)
    st.init_db(conn)
    fid = st.create_spot_feedback(conn, user_id=1, submitter='local@test.invalid',
                                  page_url='/dashboard', element_selector='.save',
                                  region_json=None, message='Save does not work')
    conn.commit()
    original_updates = conn.execute('SELECT COUNT(*) FROM feedback_update WHERE feedback_id=?', (fid,)).fetchone()[0]
    conn.close()
    with sync_playwright() as playwright:
        options = {'executable_path': os.environ['CSS_TEST_CHROMIUM']} if os.environ.get('CSS_TEST_CHROMIUM') else {}
        browser = playwright.chromium.launch(**options)
        context = browser.new_context()
        page = context.new_page()
        requests = []

        def serve(route):
            request = route.request
            url = urlsplit(request.url)
            if url.hostname != 'office.test':
                route.abort()
            elif request.method == 'GET' and url.path == f'/admin/feedback/view/{fid}':
                response = admin.get(url.path)
                assert response.status_code == 200
                route.fulfill(status=200, body=response.content, content_type='text/html')
            elif request.method == 'POST':
                requests.append((url.path, request.post_data))
                route.fulfill(status=500, body='Unexpected form submission')
            else:
                route.abort()

        page.route('**/*', serve)
        page.goto(f'http://office.test/admin/feedback/view/{fid}')
        page.evaluate('''() => {
          window.__pendingSuggestion = null;
          window.__suggestCalls = 0;
          window.fetch = () => {
            window.__suggestCalls++;
            return new Promise(resolve => { window.__pendingSuggestion = resolve; });
          };
          window.__resolveSuggestion = data => window.__pendingSuggestion({json: () => Promise.resolve(data)});
        }''')
        yield page, requests, fid
        context.close()
        browser.close()
    conn = st.connect(db_path)
    assert st.get_spot_feedback(conn, fid)['status'] == 'New'
    assert conn.execute('SELECT COUNT(*) FROM feedback_update WHERE feedback_id=?', (fid,)).fetchone()[0] == original_updates
    conn.close()


def test_suggestion_requires_explicit_save_and_escapes_reason(triage_page):
    page, requests, _ = triage_page
    page.locator('#triage-duplicate-of').fill('42')
    page.locator('#ai-suggest-btn').click()
    expect(page.locator('#ai-suggest-btn')).to_be_disabled()
    page.evaluate('''() => window.__resolveSuggestion({
      ok: true, status: 'Reviewing', severity: 'High', duplicate_of: null,
      reason: '<img src=x onerror="window.__triage_pwned=1">', interaction_id: 1,
      contract_version: 1, review_required: true
    })''')
    expect(page.locator('#triage-status')).to_have_value('Reviewing')
    expect(page.locator('#triage-severity')).to_have_value('High')
    expect(page.locator('#triage-duplicate-of')).to_have_value('')
    expect(page.locator('#ai-suggestion')).to_contain_text('review and click Save to apply')
    expect(page.locator('#ai-suggestion')).to_contain_text('<img src=x onerror=')
    assert page.locator('#ai-suggestion img').count() == 0
    assert page.evaluate('window.__triage_pwned') is None
    assert page.evaluate('window.__suggestCalls') == 1
    assert requests == []


def test_inflight_human_edits_are_preserved(triage_page):
    page, requests, _ = triage_page
    page.locator('#ai-suggest-btn').click()
    expect(page.locator('#ai-suggest-btn')).to_be_disabled()
    page.locator('input[name="admin_note"]').fill('My human decision')
    page.locator('input[name="reply"]').fill('I am investigating')
    page.locator('#triage-status').select_option('Will address')
    page.evaluate('''() => window.__resolveSuggestion({
      ok: true, status: 'Done', severity: 'Critical', duplicate_of: 3002,
      reason: 'Provider suggestion', interaction_id: 2,
      contract_version: 1, review_required: true
    })''')
    expect(page.locator('#ai-suggestion')).to_contain_text('nothing was filled in')
    expect(page.locator('#triage-status')).to_have_value('Will address')
    expect(page.locator('#triage-severity')).to_have_value('')
    expect(page.locator('#triage-duplicate-of')).to_have_value('')
    expect(page.locator('input[name="admin_note"]')).to_have_value('My human decision')
    expect(page.locator('input[name="reply"]')).to_have_value('I am investigating')
    assert requests == []
