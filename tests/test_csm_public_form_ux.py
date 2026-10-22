"""Browser checks for the public Type-1 CSM form (Spot Feedback #121): the Citizen's Charter skip rule, the
one-question-at-a-time mode with the new steps, submitting with every optional question blank, and phone width.

Optional runner: pip install playwright && python -m playwright install chromium. The browser is served by the
anonymous TestClient; every other host is blocked."""
from urllib.parse import urlsplit

import pytest

import app
import storage as st

pw = pytest.importorskip('playwright.sync_api')


from tests.test_document_guidance_browser import browser


@pytest.fixture
def walkin(app_mod):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    token = st.get_or_create_walkin_form(conn)['qr_token']
    conn.close()
    return token


@pytest.fixture
def page(browser, client):
    context = browser.new_context(viewport={'width': 390, 'height': 844}, service_workers='block')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))

    def serve(route):
        request = route.request
        url = urlsplit(request.url)
        if url.netloc != 'testserver':
            route.abort()
            return
        path = url.path + ('?' + url.query if url.query else '')
        response = client.request(request.method, path, content=request.post_data_buffer,
                                  headers={'Content-Type': request.headers.get('content-type', '')}, follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content,
                      headers={k: v for k, v in response.headers.items()
                               if k.lower() not in ('content-length', 'content-encoding', 'set-cookie')})

    page.route('**/*', serve)
    yield page
    context.close()
    assert not errors, errors


def test_not_knowing_what_a_charter_is_hides_cc2_and_cc3(page, walkin):
    page.goto(f'http://testserver/r/{walkin}')
    pw.expect(page.get_by_text('Help us serve you better!')).to_be_visible()
    cc2, cc3 = page.locator('#csm-cc2'), page.locator('#csm-cc3')
    pw.expect(cc2).to_be_visible(); pw.expect(cc3).to_be_visible()
    page.locator('[name="csm_cc2"]').first.check()
    page.locator('[name="csm_cc1"]').nth(3).check()                       # "I do not know what a CC is …"
    pw.expect(cc2).to_be_hidden(); pw.expect(cc3).to_be_hidden()
    pw.expect(page.locator('#csm-cc-skip')).to_be_visible()
    assert page.locator('[name="csm_cc2"]:checked').count() == 0          # the earlier CC2 answer was cleared
    page.locator('[name="csm_cc1"]').nth(0).check()
    pw.expect(cc2).to_be_visible(); pw.expect(cc3).to_be_visible(); pw.expect(page.locator('#csm-cc-skip')).to_be_hidden()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_the_questions_one_at_a_time_mode_walks_through_the_new_steps(page, walkin):
    page.goto(f'http://testserver/r/{walkin}')
    page.locator('#conv-toggle').click()
    pw.expect(page.locator('#f-age')).to_be_visible()                     # step 1: about you
    pw.expect(page.locator('#csm-cc')).to_be_hidden()
    page.locator('#conv-next').click()                                    # nothing in step 1 is required
    pw.expect(page.locator('#csm-cc')).to_be_visible()
    pw.expect(page.get_by_text("Citizen's Charter", exact=False).first).to_be_visible()   # the heading stays in this mode
    page.locator('#conv-next').click()                                    # CC is optional too
    pw.expect(page.get_by_text('I am satisfied with the service that I availed.')).to_be_visible()


def test_everything_optional_can_be_left_blank_and_the_form_submits(page, walkin, app_mod):
    page.goto(f'http://testserver/r/{walkin}')
    for sqd in [f'SQD{i}' for i in range(9)]:
        page.locator(f'input[name="{sqd}"][value="5"]').first.check(force=True)
    page.get_by_role('button', name='Submit').click()
    page.wait_for_load_state()
    assert 'required' not in page.url
    conn = st.connect(app_mod.DB)
    n = conn.execute("SELECT COUNT(*) FROM answer WHERE item_id='SQD8' AND value=5").fetchone()[0]
    conn.close()
    assert n >= 1


def test_a_filled_form_is_stored_with_the_client_answers(page, walkin, app_mod):
    page.goto(f'http://testserver/r/{walkin}')
    page.locator('[name="csm_client_type"][value="Citizen"]').check()
    page.locator('#f-age').fill('52')
    page.locator('#f-region').select_option('Region IV-A')
    page.locator('#f-service').fill('Data Request')
    page.locator('[name="csm_cc1"]').nth(1).check()
    page.locator('[name="csm_cc2"]').nth(2).check()
    page.locator('[name="csm_cc3"]').nth(0).check()
    for sqd in [f'SQD{i}' for i in range(9)]:
        page.locator(f'input[name="{sqd}"][value="4"]').first.check(force=True)
    page.get_by_role('button', name='Submit').click()
    page.wait_for_load_state()
    conn = st.connect(app_mod.DB)
    rows = [r for r in app._csm_blhsd_rows(conn) if r['SERVICE'] == 'Data Request' and r['AGE'] == '52']
    conn.close()
    assert rows and rows[-1]['CLIENT_TYPE'] == 'Citizen' and rows[-1]['REGION'] == 'Region IV-A'
    assert rows[-1]['CC1'] == app.CSM_CC1_OPTS[1] and rows[-1]['CC2'] == app.CSM_CC2_OPTS[2] and rows[-1]['CC3'] == app.CSM_CC3_OPTS[0]
