"""Increment 2.1: the picture grid for requesters."""
import re

import pytest
from starlette.testclient import TestClient

import auth
import supplies_requests as requests
import supplies_shop as shop
import supplies_stock as stock
from supplies_storage import Invalid
from tests.conftest import session_token
from tests.test_supplies import supplies_db, create, key, hidden
from tests.test_supplies_requests import request_db, draft, submit, get

URL = '/supplies/requests/new'


@pytest.fixture
def shop_db(request_db):
    c, u, units, path, item = request_db  # item: Synthetic paper, 10 on hand, critical 5
    limited = create(c, u[1], code='LIM-1', description='Gold stapler', unit='Box', critical_level='5')
    stock.post_opening(c, u[1], limited['id'], {'quantity': '4', 'effective_date': '2026-10-19', 'reason': 'Count'},
                       expected_revision=limited['revision'], operation_key=key())
    empty = create(c, u[1], code='EMP-1', description='Empty ink', unit='Bottle')
    return c, u, path, item, limited['id'], empty['id']


def page(app_mod, path, user, query='', **post):
    old = app_mod.DB
    app_mod.DB = path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME, session_token(user))
            return client.get(URL + query)
    finally:
        app_mod.DB = old


def card(html, name):
    return re.search(r'<li class="shop-card".*?</li>', html[html.index(name) - 600:], re.S).group(0) if name in html else ''


def test_grid_shows_picture_badge_unit_and_limits_without_stock_numbers(shop_db, app_mod):
    c, u, path, item, limited, empty = shop_db
    html = page(app_mod, path, u[2]).text
    assert html.count('<li class="shop-card"') == 3
    paper = card(html, 'Synthetic paper')
    assert 'Available' in paper and 'Ream' in paper and f'name="qty_{item}"' in paper and 'max="10"' in paper
    assert 'shop-initials' in paper and '<img' not in paper  # no picture rule for this made-up name
    stapler = card(html, 'Gold stapler')
    assert 'Limited' in stapler and 'max="4"' in stapler and '/static/img/supplies/stapler.svg' in stapler
    out = card(html, 'Empty ink')
    assert 'Out of stock' in out and 'disabled' in out and 'max="0"' in out
    content = html[html.index('<div class="supply-wrap">'):html.index('<script src="/static/js/supplies-shop.js"')].lower()
    for jargon in ('reserved', 'on hand', 'outstanding', 'revision', 'snapshot', 'issuance'):
        assert jargon not in content


def test_search_filters_by_name_code_and_unit_and_keeps_the_term(shop_db, app_mod):
    c, u, path, *_ = shop_db
    html = page(app_mod, path, u[2], '?q=stapler').text
    assert html.count('<li class="shop-card"') == 1 and 'Gold stapler' in html and 'value="stapler"' in html
    assert page(app_mod, path, u[2], '?q=bottle').text.count('<li class="shop-card"') == 1
    assert page(app_mod, path, u[2], '?q=EMP-1').text.count('<li class="shop-card"') == 1
    none = page(app_mod, path, u[2], '?q=zzzz').text
    assert 'No items match' in none and none.count('<li class="shop-card"') == 0


def test_inactive_items_are_not_offered(shop_db, app_mod):
    c, u, path, item, limited, empty = shop_db
    c.execute('UPDATE supply_item SET active=0 WHERE id=?', (empty,))
    c.commit()
    assert 'Empty ink' not in page(app_mod, path, u[2]).text


def test_classic_list_view_is_kept_for_one_release(shop_db, app_mod):
    c, u, path, *_ = shop_db
    html = page(app_mod, path, u[2], '?view=list').text
    assert html.count('<fieldset') == 20 and 'shop-card' not in html


def test_shop_page_needs_directory_linkage_like_the_old_form(shop_db, app_mod):
    c, u, path, *_ = shop_db
    assert page(app_mod, path, u[1]).status_code in (403, 422)  # custodian fixture user has no staff link


def post_grid(app_mod, path, user, quantities, **extra):
    old = app_mod.DB
    app_mod.DB = path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME, session_token(user))
            token = hidden(client.get(URL).text, 'csrf')
            data = {'csrf': token, 'operation_key': key(), 'view': 'shop', 'purpose': 'Training supplies',
                    'date_needed': '', **{f'qty_{k}': v for k, v in quantities.items()}, **extra}
            return client.post('/supplies/requests', data=data, follow_redirects=False)
    finally:
        app_mod.DB = old


def test_posting_the_grid_saves_a_draft_with_only_the_chosen_items(shop_db, app_mod):
    c, u, path, item, limited, empty = shop_db
    response = post_grid(app_mod, path, u[2], {item: '3', limited: '', empty: '0'})
    assert response.status_code == 303
    r = int(response.headers['location'].rsplit('/', 1)[1])
    entry = get(c, u, r)
    assert entry['approval_status'] == 'draft' and entry['purpose'] == 'Training supplies'
    assert [(line['item_id'], line['requested_quantity']) for line in entry['lines']] == [(item, 3)]


def test_over_limit_grid_post_is_refused_in_plain_words_and_keeps_what_was_typed(shop_db, app_mod):
    c, u, path, item, limited, empty = shop_db
    response = post_grid(app_mod, path, u[2], {item: '3', limited: '9'}, purpose='Keep this purpose')
    assert response.status_code == 422
    assert 'Only 4 boxes of Gold stapler can be requested right now.' in response.text
    assert 'Keep this purpose' in response.text and 'value="9"' in response.text and 'value="3"' in response.text
    assert c.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0


def test_out_of_stock_and_empty_posts_are_refused(shop_db, app_mod):
    c, u, path, item, limited, empty = shop_db
    out = post_grid(app_mod, path, u[2], {empty: '1'})
    assert out.status_code == 422 and 'out of stock' in out.text
    none = post_grid(app_mod, path, u[2], {item: '', limited: '0'})
    assert none.status_code == 422 and 'Pick at least one item' in none.text


def test_lines_from_form_maps_quantities_and_enforces_twenty_items():
    assert shop.lines_from_form({'qty_7': '2', 'qty_9': '', 'qty_3': '0', 'purpose': 'x', 'qty_x': '5'}) == \
        [{'item_id': '7', 'requested_quantity': '2'}]
    assert shop.chosen_quantities({'qty_7': '2', 'qty_9': ''}) == {7: '2'}
    with pytest.raises(Invalid, match='at most 20'):
        shop.lines_from_form({f'qty_{i}': '1' for i in range(1, 22)})
    with pytest.raises(Invalid):
        shop.lines_from_form({})


def test_large_catalogs_do_not_hit_the_form_field_limit(shop_db, app_mod):
    c, u, path, item, *_ = shop_db
    response = post_grid(app_mod, path, u[2], {**{1000 + i: '' for i in range(400)}, item: '2'})
    assert response.status_code == 303


def test_shop_script_is_served_and_accessible(shop_db, app_mod):
    c, u, path, *_ = shop_db
    old = app_mod.DB
    app_mod.DB = path
    try:
        with TestClient(app_mod.app) as client:
            js = client.get('/static/js/supplies-shop.js')
            assert js.status_code == 200 and "aria-label" in js.text and 'shop-bar' in js.text
    finally:
        app_mod.DB = old
