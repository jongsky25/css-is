"""Browser regressions for claim entry and preparation.

Optional runner: pip install playwright && python -m playwright install chromium
The browser is served by the authenticated TestClient; Google and all other
external requests are blocked. Generated documents use the recording relay.
"""
from urllib.parse import urlsplit

import pytest

from test_travel_generate import conn, relay, mk, items  # shared travel fixtures

pw = pytest.importorskip('playwright.sync_api')


@pytest.fixture(scope='module')
def browser():
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except pw.Error as e:
            if "Executable doesn't exist" in str(e):
                pytest.skip('Install Chromium with python -m playwright install chromium')
            raise
        yield browser
        browser.close()


@pytest.fixture
def page(browser, viewer):
    context = browser.new_context(viewport={'width': 390, 'height': 844})
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
        response = viewer.request(request.method, path, content=request.post_data_buffer,
                                  headers={'Content-Type': request.headers.get('content-type', '')},
                                  follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content,
                      headers={k: v for k, v in response.headers.items()
                               if k.lower() not in ('content-length', 'content-encoding', 'set-cookie')})

    page.route('**/*', serve)
    yield page
    context.close()
    assert not errors, errors


def test_kind_switch_hides_irrelevant_answers_and_preserves_them(page, conn):
    page.goto('http://testserver/travel/new')
    gas = page.locator('[name="official_gasoline"]')
    refund = page.locator('[name="refund"]')
    pw.expect(gas).to_be_visible()
    gas.check()
    pw.expect(refund).not_to_be_visible()
    page.locator('[name="kind"][value="liquidation"]').check()
    pw.expect(gas).not_to_be_visible()
    pw.expect(gas).to_be_disabled()
    pw.expect(refund).to_be_visible()
    pw.expect(page.locator('#external-advance')).to_be_visible()
    page.locator('[name="kind"][value="reimbursement"]').check()
    pw.expect(page.locator('#liq-fields')).not_to_be_visible()
    pw.expect(refund).to_be_disabled()
    page.locator('[name="kind"][value="ca"]').check()
    pw.expect(gas).to_be_checked()
    pw.expect(gas).to_be_enabled()


@pytest.mark.parametrize('kind', ['ca', 'reimbursement', 'liquidation'])
def test_preparation_only_shows_applicable_forms(page, viewer, conn, relay, kind):
    from datetime import timedelta
    import tzutil as tz
    extra = {'kind': kind}
    if kind == 'ca':
        extra.update(start=(tz.today_local() + timedelta(days=20)).isoformat(),
                     end=(tz.today_local() + timedelta(days=22)).isoformat())
    ref = mk(viewer, **extra)
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    report = page.get_by_role('heading', name='Post travel report', exact=True)
    completion = page.get_by_role('heading', name='Certificate of travel completed', exact=True)
    if kind == 'ca':
        pw.expect(report).to_have_count(0)
        pw.expect(completion).to_have_count(0)
    else:
        pw.expect(report).to_be_visible()
        pw.expect(completion).to_be_visible()
        pw.expect(page.get_by_label('Explanation (if it did not go as planned)', exact=True)).not_to_be_visible()
        page.get_by_label('How the travel went', exact=True).select_option('cut')
        pw.expect(page.get_by_label('Explanation (if it did not go as planned)', exact=True)).to_be_visible()
    pw.expect(page.get_by_role('heading', name='Job Order certification', exact=True)).to_have_count(0)
    pw.expect(page.get_by_role('heading', name='MC 114 justification', exact=True)).to_have_count(0)
    pw.expect(page.get_by_label('Refund amount (₱)', exact=True)).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_applicable_certification_justification_and_refund_are_available(page, viewer, conn, relay):
    ref = mk(viewer, jo_cos='1', refund='1', mc114_format='appendix_b')
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    pw.expect(page.get_by_role('heading', name='Job Order certification', exact=True)).to_be_visible()
    pw.expect(page.get_by_role('heading', name='MC 114 justification', exact=True)).to_be_visible()
    pw.expect(page.get_by_label('Refund amount (₱)', exact=True)).to_be_visible()


def test_actual_fare_survives_policy_calculation_and_browser_reload(page, viewer, conn, relay):
    ref = mk(viewer)
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    page.get_by_label('How you travelled', exact=True).first.select_option('taxi')
    page.get_by_label('Fare rate', exact=True).first.select_option('live_out')
    distance = page.get_by_label('Distance by Google Maps (km)', exact=True).first
    distance.fill('10')
    pw.expect(page.get_by_text('Most allowed for this ride:', exact=False).first).to_be_visible()
    fare = page.get_by_label('Actual fare claimed (₱)', exact=True).first
    pw.expect(fare).to_have_value('0')
    fare.fill('75')
    distance.fill('12')
    pw.expect(fare).to_have_value('75')
    pw.expect(page.locator('#draft-status')).to_contain_text('Draft saved in this browser only')
    page.reload()
    pw.expect(page.get_by_label('Actual fare claimed (₱)', exact=True).first).to_have_value('75')
    pw.expect(page.locator('#draft-status')).to_contain_text('Draft restored')
    page.get_by_role('button', name='Make the forms', exact=True).click()
    pw.expect(page.get_by_text('Done. Open each form', exact=False)).to_be_visible(timeout=15000)
    assert items(conn, ref)['appendix_b']['doc_url']
    assert relay.calls
    pw.expect(page.get_by_role('link', name='Continue to checklist')).to_have_attribute('href', f'/travel/f/{ref}')


def test_unconfigured_relay_cannot_be_enabled_by_status_poll(page, viewer, conn, monkeypatch):
    import gdocs_relay as gr
    monkeypatch.delenv(gr.ENV_URL, raising=False)
    monkeypatch.delenv(gr.ENV_SECRET, raising=False)
    ref = mk(viewer)
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    pw.expect(page.get_by_role('button', name='Make the forms', exact=True)).to_be_disabled()
    pw.expect(page.get_by_text('Some forms did not finish.', exact=False)).to_have_count(0)


def test_estimate_can_use_policy_but_does_not_replace_manual_amount(page, viewer, conn, relay):
    from datetime import timedelta
    import tzutil as tz
    ref = mk(viewer, kind='ca', start=(tz.today_local() + timedelta(days=20)).isoformat(),
             end=(tz.today_local() + timedelta(days=22)).isoformat())
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    page.get_by_label('How you travelled', exact=True).first.select_option('taxi')
    page.get_by_label('Fare rate', exact=True).first.select_option('activity')
    fare = page.get_by_label('Estimated fare (₱)', exact=True).first
    pw.expect(fare).to_have_value('550')
    fare.fill('250')
    with page.expect_response('**/rates'):
        page.get_by_label('How you travelled', exact=True).first.select_option('tnvs')
    pw.expect(fare).to_have_value('250')


def test_storage_failure_is_visible_and_hidden_refund_is_not_generated(page, viewer, conn, relay):
    ref = mk(viewer, kind='reimbursement')
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    # An older browser draft may contain refund fields from prior answers.
    page.get_by_label('Purpose (completes "To …")', exact=True).fill('attend meeting')
    page.evaluate('''ref => {
      const key = 'travel-draft-' + ref;
      const d = JSON.parse(localStorage.getItem(key));
      d.texts.refund_amount = '800'; d.texts.refund_or_no = 'OLD-RECEIPT';
      d.texts.explanation = 'Old deviation'; d.texts.strictness = 'strict';
      localStorage.setItem(key, JSON.stringify(d));
    }''', ref)
    page.reload()
    page.evaluate("() => { Storage.prototype.setItem = function () { throw new Error('full'); }; }")
    page.get_by_label('Purpose (completes "To …")', exact=True).fill('attend workshop')
    pw.expect(page.locator('#draft-status')).to_contain_text('Draft could not be saved')
    page.get_by_role('button', name='Make the forms', exact=True).click()
    pw.expect(page.get_by_text('Done. Open each form', exact=False)).to_be_visible(timeout=15000)
    appendix = next(c for c in relay.calls if c['template_key'] == 'appendix_b')
    assert appendix['fields']['refund_amount'] == ''
    assert appendix['fields']['refund_or_no'] == ''
    assert 'Old deviation' not in str(appendix['blocks'])


def test_per_diem_box_stays_out_of_the_way_when_the_policy_gives_the_amount(page, viewer, conn, relay):
    """Spot Feedback #119: with a per diem rule chosen the amount comes from the policy rates, so the box is hidden
    until the person asks to change it; typing the per diem yourself still shows it."""
    ref = mk(viewer)
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    box = page.get_by_label('Per diem (₱)', exact=True).first
    pw.expect(box).to_be_visible()                                              # no rate chosen yet: type it yourself
    region = page.get_by_label('Where you are going', exact=True)
    region.select_option(index=1)
    page.get_by_label('Per diem rule', exact=True).first.select_option(index=1)
    pw.expect(page.get_by_text('Per diem for this day, from the policy rates:', exact=False).first).to_be_visible()
    pw.expect(box).to_be_hidden()
    page.get_by_role('button', name='Change amount', exact=True).first.click()
    pw.expect(box).to_be_visible()
    box.fill('100')
    pw.expect(box).to_have_value('100')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_a_day_can_hold_a_plane_ride_and_a_tnvs_ride_to_or_from_the_airport(page, viewer, conn, relay):
    """Spot Feedback #120/#124: several rides on one day are several entries on the same date."""
    ref = mk(viewer)
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    modes = page.get_by_label('How you travelled', exact=True)
    n = modes.count()
    modes.first.select_option('plane')
    page.get_by_role('button', name='Add TNVS to the airport', exact=True).first.click()
    pw.expect(modes).to_have_count(n + 1)
    first_date = page.get_by_label('Date', exact=True).nth(0).input_value()
    assert page.get_by_label('Date', exact=True).nth(1).input_value() == first_date
    pw.expect(modes.nth(1)).to_have_value('tnvs')
    pw.expect(page.get_by_label('To', exact=True).nth(1)).to_have_value('Airport')
    pw.expect(page.get_by_text('Another ride on the same day', exact=False)).to_have_count(1)
    page.get_by_role('button', name='Add TNVS from the airport', exact=True).first.click()
    pw.expect(modes).to_have_count(n + 2)
    pw.expect(page.get_by_label('From', exact=True).nth(1)).to_have_value('Airport')   # the newest ride sits right after the plane
    page.get_by_role('button', name='Add another ride on this day', exact=True).last.click()
    pw.expect(modes).to_have_count(n + 3)
    # a day's per diem is claimed once
    for i in (0, 1):
        page.get_by_label('Per diem (₱)', exact=True).nth(i).fill('500')
    pw.expect(page.get_by_text('both claim a per diem', exact=False)).to_be_visible()
    page.reload()
    pw.expect(modes).to_have_count(n + 3)                                               # the draft keeps them
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_drafted_entries_keep_edits_take_new_uploads_and_stay_removed(page, viewer, conn, relay):
    """Appendix A drafted from what was read (Spot Feedback #122/#123): each entry says where it came from, a browser
    draft keeps what the person changed, picks up uploads read since, and an entry they removed does not come back."""
    from datetime import timedelta
    import tzutil as tz
    import travel, travel_readings as trd
    ref = mk(viewer, flew='1', taxi_receipt='1')
    fid = travel.get_by_ref(conn, ref)['id']
    day = (tz.today_local() - timedelta(days=10)).isoformat()
    trd.save(conn, fid, 'plane_ticket', 'receipt', {'readable': True, 'kind': 'plane_ticket', 'amount': 4521.5, 'currency': 'PHP',
                                                    'date': day, 'origin': 'Manila', 'destination': 'Cebu', 'vendor': 'Cebu Pacific'})
    page.goto(f'http://testserver/travel/f/{ref}/prepare')
    modes = page.get_by_label('How you travelled', exact=True)
    pw.expect(modes.first).to_have_value('plane')
    pw.expect(page.get_by_text('Drafted from your upload', exact=False)).to_have_count(1)
    fare = page.get_by_label('Actual fare claimed (₱)', exact=True).first
    pw.expect(fare).to_have_value('4521.5')
    fare.fill('4000')                                              # the person corrects the amount
    rows = modes.count()
    trd.save(conn, fid, 'taxi_receipt', 'receipt', {'readable': True, 'kind': 'taxi_receipt', 'amount': 350.0, 'currency': 'PHP',
                                                    'date': day, 'origin': 'Airport', 'destination': 'Hotel'})
    page.reload()
    pw.expect(page.locator('#draft-status')).to_contain_text('1 entry added from files you uploaded since')
    pw.expect(modes).to_have_count(rows + 1)
    pw.expect(page.get_by_label('Actual fare claimed (₱)', exact=True).first).to_have_value('4000')   # the edit survived
    assert page.get_by_label('Actual fare claimed (₱)', exact=True).evaluate_all('els => els.map(e => e.value)').count('350') == 1
    page.get_by_role('button', name='Remove this entry', exact=True).last.click()                       # the taxi entry (added last)
    pw.expect(modes).to_have_count(rows)
    page.reload()
    pw.expect(modes).to_have_count(rows)                                                              # it stays removed
    assert page.get_by_label('Actual fare claimed (₱)', exact=True).evaluate_all('els => els.map(e => e.value)').count('350') == 0
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
