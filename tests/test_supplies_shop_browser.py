"""Supplies 2.1 in a real browser: the picture grid at phone and desktop width, the + / - buttons, search and the bar."""
import os
import sqlite3
from urllib.parse import urlsplit

import pytest

import storage as st
import supplies as s
from conftest import in_the_directory
from tests.test_document_registry_grid_browser import grid_browser  # noqa: F401
from tests.test_supplies import key
from tests.test_supplies_stock import opening

SHOTS = os.environ.get('SHOP_SHOTS', '')          # a folder to keep screenshots in, when asked


@pytest.fixture
def shop_page(grid_browser, app_mod, viewer):
    directory = in_the_directory(app_mod, 'viewer@test.local', path='SHOPFX/D1/S1')
    directory.__enter__()
    try:
        c = st.connect(app_mod.DB)
        admin = st.get_admin_user(c, 'admin@test.local')
        user = st.get_admin_user(c, 'viewer@test.local')
        s.grant_role(c, admin, user['id'], 'custodian', operation_key=key())
        s.set_enabled(c, admin, '1', expected_revision=0, operation_key=key())
        names = [('A4 Bond Paper', 'ream', 12), ('Ballpen (Blue)', 'box', 3), ('Fancy Folder (Red)', 'pack', 0),
                 ('Stapler', 'piece', 7), ('Masking Tape', 'roll', 40)]
        for i, (name, unit, qty) in enumerate(names):
            item = s.create_item(c, user, {'code': f'SHOP-{i}', 'description': name, 'unit': unit, 'critical_level': '5',
                                           'target_level': '20'}, operation_key=key())
            if qty:
                opening(c, user, item, quantity=str(qty))
        context = grid_browser.new_context(viewport={'width': 375, 'height': 800})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def serve(route):
            url = urlsplit(route.request.url)
            if url.hostname != 'office.test':
                route.abort()
                return
            response = viewer.request(route.request.method, url.path + ('?' + url.query if url.query else ''),
                                      content=route.request.post_data_buffer,
                                      headers={k: v for k, v in route.request.headers.items() if k.lower() in ('content-type', 'x-csrf-token')},
                                      follow_redirects=False)
            if 300 <= response.status_code < 400 and response.headers.get('location'):     # a fulfilled redirect is not followed
                route.fulfill(status=200, content_type='text/html',
                              body='<meta http-equiv="refresh" content="0;url=' + response.headers['location'] + '">')
                return
            route.fulfill(status=response.status_code, body=response.content,
                          headers={k: v for k, v in response.headers.items() if k.lower() not in ('content-length', 'content-encoding', 'set-cookie')})
        page.route('**/*', serve)
        page.goto('http://office.test/supplies/requests/new')
        yield page, errors
        assert errors == []
        context.close()
        c.close()
    finally:
        try:
            directory.__exit__(None, None, None)
        except sqlite3.IntegrityError:               # a request the test sent still points at the temporary person
            pass


def shot(page, name, full=True):
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, name), full_page=full)


def test_the_grid_fits_a_phone_and_the_buttons_work(shop_page):
    page, _ = shop_page
    page.locator('.shop-card').first.wait_for()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')          # no sideways scrolling at 375 px
    shot(page, 'shop-375.png')
    card = page.locator('.shop-card', has_text='Ballpen (Blue)')                                # 3 on hand
    plus = card.get_by_role('button', name='One more', exact=False)
    for _ in range(6):
        plus.click()
    assert card.locator('input').input_value() == '3'                                           # the box stops at what can be asked for
    card.get_by_role('button', name='One less', exact=False).click()
    assert card.locator('input').input_value() == '2'
    page.locator('.shop-card', has_text='A4 Bond Paper').get_by_role('button', name='One more', exact=False).click()
    assert page.locator('[data-shop-count]').inner_text() == '2 items chosen'
    out = page.locator('.shop-card', has_text='Fancy Folder')
    assert out.locator('input').is_disabled() and 'Out of stock' in out.inner_text()
    assert out.get_by_role('button').count() == 0                                               # nothing to press on an unavailable item


def test_search_hides_cards_without_losing_what_was_typed(shop_page):
    page, _ = shop_page
    page.locator('.shop-card').first.wait_for()
    page.locator('.shop-card', has_text='Stapler').locator('input').fill('2')
    page.locator('#shop-q').fill('tape')
    assert page.locator('.shop-card:visible').count() == 1 and 'Masking Tape' in page.locator('.shop-card:visible').inner_text()
    page.locator('#shop-q').fill('')
    assert page.locator('.shop-card:visible').count() == 5
    assert page.locator('.shop-card', has_text='Stapler').locator('input').input_value() == '2'


def test_the_form_sends_what_was_chosen_and_the_bar_does_not_cover_the_feedback_button(shop_page):
    page, _ = shop_page
    page.locator('.shop-card').first.wait_for()
    page.locator('.shop-card', has_text='A4 Bond Paper').locator('input').fill('4')
    page.locator('.shop-card', has_text='Stapler').get_by_role('button', name='One more', exact=False).click()
    page.locator('#request-purpose').fill('Browser synthetic purpose')
    sent = page.evaluate("Object.fromEntries([...new FormData(document.querySelector('[data-shop]')).entries()].filter(e => e[1] !== ''))")
    quantities = {k: v for k, v in sent.items() if k.startswith('qty_')}
    assert sorted(quantities.values()) == ['1', '4'] and sent['purpose'] == 'Browser synthetic purpose' and sent['view'] == 'grid'
    assert not any(k.startswith('qty_') and v == '' for k, v in sent.items())
    # the bar's Save draft button must not sit under the floating feedback button
    page.evaluate("window.scrollTo(0, 0)")
    save = page.get_by_role('button', name='Save draft').bounding_box()
    bubble = page.locator('#sfBtn').bounding_box()
    if bubble:
        assert save['x'] + save['width'] <= bubble['x'] or save['y'] + save['height'] <= bubble['y'] or bubble['y'] + bubble['height'] <= save['y']
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto('http://office.test/supplies/requests/new')
    page.locator('.shop-card').first.wait_for()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    shot(page, 'shop-1280.png')


def test_the_search_box_stays_in_view_and_finds_items_by_other_names(shop_page):
    page, _ = shop_page
    page.locator('.shop-card').first.wait_for()
    page.set_viewport_size({'width': 375, 'height': 420})                                       # a short screen, so the page must scroll
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    box = page.locator('#shop-q').bounding_box()
    nav = page.locator('.topnav').bounding_box()
    assert box and 0 <= box['y'] and box['y'] >= nav['y'] + nav['height'] - 1                    # visible, and not under the site header
    shot(page, 'shop-pinned-375.png', full=False)
    page.locator('#shop-q').fill('ballpoint')                                                   # an alternative name for "Ballpen"
    assert page.locator('.shop-card:visible').count() == 1 and 'Ballpen' in page.locator('.shop-card:visible').inner_text()
    page.locator('#shop-q').fill('staplr')                                                      # a typo
    assert page.locator('.shop-card:visible').count() == 1 and 'Stapler' in page.locator('.shop-card:visible').inner_text()
    page.locator('#shop-q').fill('pan')                                                         # three letters stay exact
    assert page.locator('.shop-card:visible').count() == 0


def test_the_plain_list_search_filters_the_drop_downs_and_keeps_a_choice(shop_page):
    page, _ = shop_page
    page.goto('http://office.test/supplies/requests/new?view=list')
    page.locator('select[name="item_0"]').wait_for()
    first = page.locator('select[name="item_0"]')
    first.select_option(label=first.locator('option', has_text='Masking Tape').inner_text())
    page.locator('#list-q').fill('staplr')
    options = page.locator('select[name="item_1"] option')
    texts = [options.nth(i).inner_text() for i in range(options.count())]
    assert any('Stapler' in t for t in texts) and not any('Masking' in t for t in texts) and not any('Ballpen' in t for t in texts)
    assert 'Masking Tape' in first.locator('option:checked').inner_text()                         # what was already chosen stays
    page.locator('#list-q').fill('')
    assert page.locator('select[name="item_1"] option').count() == 6                              # five items and "Choose an item"


def test_review_opens_the_cart_which_fits_a_phone_and_send_submits_it(shop_page):
    page, _ = shop_page
    page.locator('.shop-card').first.wait_for()
    page.locator('.shop-card', has_text='A4 Bond Paper').locator('input').fill('4')
    page.locator('.shop-card', has_text='Stapler').get_by_role('button', name='One more', exact=False).click()
    page.locator('#request-purpose').fill('Browser cart purpose')
    page.get_by_role('button', name='Review').click()
    page.get_by_role('heading', name='Review your request').wait_for()
    assert page.locator('.cart-line').count() == 2 and page.locator('#request-purpose').input_value() == 'Browser cart purpose'
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    shot(page, 'cart-375.png')
    send = page.get_by_role('button', name='Send request').bounding_box()
    bubble = page.locator('#sfBtn').bounding_box()
    if bubble:
        assert send['x'] + send['width'] <= bubble['x'] or send['y'] + send['height'] <= bubble['y'] or bubble['y'] + bubble['height'] <= send['y']
    page.locator('.cart-line', has_text='Stapler').get_by_role('button', name='One more', exact=False).click()
    page.get_by_role('button', name='Choose more').click()                       # back to the grid keeps what was chosen
    page.locator('.shop-card', has_text='Stapler').wait_for()
    assert page.locator('.shop-card', has_text='Stapler').locator('input').input_value() == '2'
    page.get_by_role('button', name='Review').click()
    page.get_by_role('button', name='Send request').click()
    page.wait_for_url('**/supplies/requests/1')
    page.wait_for_load_state('load')
    assert 'SUP-' in page.content() and 'Browser cart purpose' in page.content()
