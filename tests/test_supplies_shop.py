"""Supplies 2.1: the requester's picture grid (cards, badges, limits, search, saving a draft)."""
import pytest
from starlette.testclient import TestClient

import auth
import supplies_requests as requests
import supplies_shop as shop
import supplies_stock as stock
from tests.test_supplies import key, hidden, create, supplies_db  # noqa: F401
from tests.test_supplies_requests import request_db, get  # noqa: F401  (shared fixtures)
from tests.conftest import session_token


def second_item(c, u, qty, **changes):
    item = create(c, u[1], code='SH2', description='Ballpen Black', **changes)['id']
    if qty:
        stock.post_opening(c, u[1], item, {'quantity': str(qty), 'effective_date': '2026-10-19', 'reason': 'Synthetic opening'},
                           expected_revision=1, operation_key=key())
    return item


def client_for(app_mod, path, user):
    old = app_mod.DB
    app_mod.DB = path
    client = TestClient(app_mod.app)
    client.__enter__()
    client.cookies.set(auth.COOKIE_NAME, session_token(user))
    return client, old


def test_cards_carry_the_badge_and_the_most_that_can_be_requested(request_db):
    c, u, _, _, item = request_db                    # 10 on hand
    out = second_item(c, u, 0)
    cards = {x['id']: x for x in shop.shop_items(c)}
    assert cards[item]['max'] == 10 and cards[item]['badge'] in ('Available', 'Limited') and cards[item]['unit']
    assert cards[out]['max'] == 0 and cards[out]['badge'] == 'Out of stock' and cards[out]['tone'] == 'out'
    # another person's submitted request comes off the amount that can be requested (rule R1)
    requests.submit(c, u[3], requests.save_draft(c, u[3], {'purpose': 'x', 'date_needed': '', 'lines': [
        {'item_id': item, 'requested_quantity': '4'}]}, operation_key=key())['id'], expected_revision=1, operation_key=key())
    assert {x['id']: x for x in shop.shop_items(c)}[item]['max'] == 6


def test_search_matches_every_word_in_the_name_or_code(request_db):
    c, u, _, _, item = request_db
    second_item(c, u, 5)
    names = lambda q: [x['description'] for x in shop.shop_items(c, q)]
    assert 'Ballpen Black' in names('ball')
    assert names('ballpen black') == ['Ballpen Black'] and names('zzz') == []
    assert names('  ') == names('') and len(names('')) == 2
    assert names('sh2') == ['Ballpen Black']                                   # the code matches too


def test_tiles_show_initials_without_pictures_and_never_fail():
    t = shop.tile('Ballpen Black', 'SH2')
    assert t['initials'] == 'BB' and t['tint'].startswith('#') and t['src'] in ('', t['src'])
    assert shop.tile('', '')['initials'] == ''


def test_quantities_come_from_the_grid_boxes_in_item_order():
    got = shop.quantities_from({'qty_12': '3', 'qty_4': ' 2 ', 'qty_9': '', 'qty_7': '0', 'qty_x': '5', 'purpose': 'p', 'qty_30': 'abc'})
    assert got == [{'item_id': '4', 'requested_quantity': '2'}, {'item_id': '12', 'requested_quantity': '3'},
                   {'item_id': '30', 'requested_quantity': 'abc'}]           # bad numbers reach the service, which refuses them


def test_a_new_request_opens_the_grid_and_the_plain_list_is_still_there(request_db, app_mod):
    c, u, _, path, item = request_db
    out = second_item(c, u, 0)
    client, old = client_for(app_mod, path, u[2])
    try:
        page = client.get('/supplies/requests/new').text
        assert 'class="shop-grid"' in page and f'name="qty_{item}"' in page and f'max="10"' in page
        assert f'name="qty_{out}"' in page and 'Out of stock' in page and 'disabled' in page.split(f'name="qty_{out}"')[1].split('>')[0]
        assert 'Use the plain list instead' in page and 'count(' not in page
        assert '<fieldset' not in page and hidden(page, 'csrf')
        assert 'class="shop-grid"' not in client.get('/supplies/requests/new?view=list').text
        assert client.get('/supplies/requests/new?view=list').text.count('<fieldset') == 20
        found = client.get('/supplies/requests/new?q=ballpen').text
        assert 'Ballpen Black' in found and found.count('class="shop-card') == 1
        nothing = client.get('/supplies/requests/new?q=zzzz').text
        assert 'Nothing in the catalog matches' in nothing and 'shop-card' not in nothing
        assert client.get('/supplies/requests/new?q=' + 'x' * 500).status_code == 200      # a long search is just cut
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_saving_from_the_grid_makes_a_draft_with_the_chosen_items(request_db, app_mod):
    c, u, _, path, item = request_db
    other = second_item(c, u, 5)
    client, old = client_for(app_mod, path, u[2])
    try:
        token = hidden(client.get('/supplies/requests/new').text, 'csrf')
        data = {'csrf': token, 'operation_key': key(), 'view': 'grid', 'purpose': 'Grid synthetic purpose', 'date_needed': '',
                f'qty_{item}': '3', f'qty_{other}': '2'}
        data.update({f'qty_{900 + i}': '' for i in range(150)})                    # empty boxes of a long catalog are posted too
        result = client.post('/supplies/requests', data=data, follow_redirects=False)
        assert result.status_code == 303
        r = int(result.headers['location'].rsplit('/', 1)[1])
        lines = {ln['item_id']: ln['requested_quantity'] for ln in get(c, u, r)['lines']}
        assert lines == {item: 3, other: 2}
        assert client.post('/supplies/requests', data=data, follow_redirects=False).headers['location'] == result.headers['location']
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_asking_for_more_than_can_be_requested_is_refused_and_the_grid_keeps_what_was_typed(request_db, app_mod):
    c, u, _, path, item = request_db                                              # 10 on hand
    client, old = client_for(app_mod, path, u[2])
    try:
        token = hidden(client.get('/supplies/requests/new').text, 'csrf')
        data = {'csrf': token, 'operation_key': key(), 'view': 'grid', 'purpose': '<b>Keep me</b>', 'date_needed': '',
                f'qty_{item}': '11'}
        bad = client.post('/supplies/requests', data=data)
        assert bad.status_code == 422 and 'class="shop-grid"' in bad.text
        assert 'Only 10' in bad.text and 'value="11"' in bad.text and '&lt;b&gt;Keep me&lt;/b&gt;' in bad.text
        assert c.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0
        none = client.post('/supplies/requests', data={**data, 'operation_key': key(), f'qty_{item}': ''})
        assert none.status_code == 422                                              # a request needs at least one item
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_editing_a_saved_draft_still_uses_the_plain_form(request_db, app_mod):
    c, u, _, path, item = request_db
    client, old = client_for(app_mod, path, u[2])
    try:
        token = hidden(client.get('/supplies/requests/new').text, 'csrf')
        r = client.post('/supplies/requests', data={'csrf': token, 'operation_key': key(), 'view': 'grid', 'purpose': 'p',
                                                    'date_needed': '', f'qty_{item}': '2'}, follow_redirects=False)
        edit = client.get(r.headers['location'] + '/edit').text
        assert 'class="shop-grid"' not in edit and edit.count('<fieldset') == 20
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old
