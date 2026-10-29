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


def test_tiles_use_the_item_pictures_and_fall_back_to_initials_without_failing():
    named = shop.tile('Ballpen Black', 'SH2')                                  # Supplies 1.4 picks a picture from the name
    assert named['src'].endswith('ballpen.svg') and named['initials'] == '' and named['tint'].startswith('#')
    unknown = shop.tile('Zebra Gadget', 'ZG1')                                 # nothing matches: a tile with the initials
    assert unknown['initials'] == 'ZG' and unknown['tint'].startswith('#')
    assert shop.tile('', '')['initials'] == ''


def test_the_grid_shows_a_picture_for_a_known_item_and_initials_for_an_unknown_one(request_db, app_mod):
    c, u, _, path, item = request_db
    second_item(c, u, 5)                                                       # "Ballpen Black"
    create(c, u[1], code='ZG1', description='Zebra Gadget')
    client, old = client_for(app_mod, path, u[2])
    try:
        page = client.get('/supplies/requests/new').text
        assert '/static/img/supplies/ballpen.svg' in page
        assert '<span>ZG</span>' in page
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


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


# ---- the search: wider matching, the plain list's search box ---------------------------------------------------------

@pytest.mark.parametrize("name, typed, found", [
    ("Ballpen (Blue)", "pen", True), ("Ballpen (Blue)", "ballpoint", True), ("Air Freshner", "freshener", True),
    ("A4 Bond Paper", "copy paper", True), ("Scissor", "scissors", True), ("Masking Tape", "maskin", True),
    ("Post it Notes 3x3", "sticky", True), ("Cartolina", "cartolna", True), ("A4 Bond Paper", "bond a4", True),
    ("Stapler", "pan", False), ("Pencil", "pan", False), ("Cartolina", "xyz", False), ("Stapler", "staple remover", False),
    ("Tape", "tap", True), ("Scissor", "sicssor", True), ("Stapler", "staplre", True)])
def test_the_search_finds_alternative_names_plurals_and_one_typo(name, typed, found):
    assert shop.text_matches(shop.search_text(name), shop._words(typed)) is found


def test_a_typo_needs_four_letters_so_short_words_stay_exact():
    assert shop._within_one('cartolna', 'cartolina') and shop._within_one('scisor', 'scissor') and shop._within_one('sicssor', 'scissor')
    assert not shop._within_one('stapel', 'stapler') and not shop._within_one('abcd', 'badc')      # two edits, or two swaps, are too far
    assert not shop.text_matches('pencil', ['pan'])                   # three letters: no typo allowed
    assert shop.text_matches('pencil', ['pencl'])                     # five letters: one typo allowed


def test_the_cards_carry_the_search_words(request_db):
    c, u, _, _, item = request_db
    second_item(c, u, 5)
    ball = next(x for x in shop.shop_items(c) if x['description'] == 'Ballpen Black')
    assert 'ballpoint' in ball['search'] and 'sh2' in ball['search']
    assert [x['description'] for x in shop.shop_items(c, 'ballpoint')] == ['Ballpen Black']
    assert [x['description'] for x in shop.shop_items(c, 'ballpn')] == ['Ballpen Black']       # one letter missing


def test_the_plain_list_has_a_search_box_that_narrows_the_drop_downs(request_db, app_mod):
    c, u, _, path, item = request_db
    second_item(c, u, 5)
    client, old = client_for(app_mod, path, u[2])
    try:
        plain = client.get('/supplies/requests/new?view=list').text
        assert 'data-list-search' in plain and plain.count('Ballpen Black') >= 20 and plain.count('<fieldset') == 20
        narrowed = client.get('/supplies/requests/new?view=list&q=ballpoint').text
        assert 'Ballpen Black' in narrowed and 'Synthetic paper' not in narrowed and narrowed.count('<fieldset') == 20
        assert 'Show everything' in narrowed and 'value="ballpoint"' in narrowed
        # an item already chosen on a form sent back with an error stays in the drop-down whatever was typed
        token = hidden(client.get('/supplies/requests/new?view=list').text, 'csrf')
        back = client.post('/supplies/requests', data={'csrf': token, 'operation_key': key(), 'purpose': 'p', 'date_needed': '',
                                                       'item_0': str(item), 'quantity_0': '999'})
        assert back.status_code == 422 and f'value="{item}" data-search' in back.text
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_editing_a_draft_has_the_script_only_search_box(request_db, app_mod):
    c, u, _, path, item = request_db
    client, old = client_for(app_mod, path, u[2])
    try:
        token = hidden(client.get('/supplies/requests/new').text, 'csrf')
        r = client.post('/supplies/requests', data={'csrf': token, 'operation_key': key(), 'view': 'grid', 'purpose': 'p',
                                                    'date_needed': '', f'qty_{item}': '2'}, follow_redirects=False)
        edit = client.get(r.headers['location'] + '/edit').text
        assert 'data-list-search' in edit and 'method="get"' not in edit.split('<form method="post"')[0].split('role="search"')[-1]
        assert 'supplies-shop.js' in edit
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


# ---- Supplies 2.2: the cart review and one-step send ----

def cart_data(client, item, qty, **extra):
    token = hidden(client.get('/supplies/requests/new').text, 'csrf')
    return {'csrf': token, 'operation_key': key(), 'submit_operation_key': key(), 'view': 'grid',
            'purpose': 'Cart synthetic purpose', 'date_needed': '', f'qty_{item}': str(qty), **extra}


def test_review_shows_the_cart_with_pictures_and_editable_numbers_and_back_keeps_them(request_db, app_mod):
    c, u, _, path, item = request_db
    other = second_item(c, u, 5)
    client, old = client_for(app_mod, path, u[2])
    try:
        data = cart_data(client, item, 3, **{f'qty_{other}': '2', 'qty_999': ''})
        page = client.post('/supplies/requests/review', data=data)
        assert page.status_code == 200 and 'Review your request' in page.text
        assert f'name="qty_{item}"' in page.text and 'value="3"' in page.text and 'value="2"' in page.text
        assert '/static/img/supplies/ballpen.svg' in page.text and 'Send request' in page.text and 'Save for later' in page.text
        assert 'Cart synthetic purpose' in page.text and 'qty_999' not in page.text
        assert c.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0          # reviewing writes nothing
        back = client.post('/supplies/requests/review', data={**data, 'step': 'grid'})
        assert 'class="shop-grid"' in back.text and 'value="3"' in back.text and 'Cart synthetic purpose' in back.text
        empty = client.post('/supplies/requests/review', data={**data, f'qty_{item}': '', f'qty_{other}': ''})
        assert empty.status_code == 422 and 'Choose at least one item' in empty.text and 'class="shop-grid"' in empty.text
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_send_saves_and_submits_in_one_step_and_a_repeat_post_does_nothing_new(request_db, app_mod):
    c, u, _, path, item = request_db
    client, old = client_for(app_mod, path, u[2])
    try:
        data = cart_data(client, item, 4, act='send')
        sent = client.post('/supplies/requests/send', data=data, follow_redirects=False)
        assert sent.status_code == 303
        r = int(sent.headers['location'].rsplit('/', 1)[1])
        got = get(c, u, r)
        assert got['approval_status'] == 'submitted' and got['control_number'].startswith('SUP-')
        assert {ln['item_id']: ln['requested_quantity'] for ln in got['lines']} == {item: 4}
        again = client.post('/supplies/requests/send', data=data, follow_redirects=False)
        assert again.headers['location'] == sent.headers['location']
        assert c.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 1
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_save_for_later_keeps_a_draft_that_is_not_sent(request_db, app_mod):
    c, u, _, path, item = request_db
    client, old = client_for(app_mod, path, u[2])
    try:
        saved = client.post('/supplies/requests/send', data=cart_data(client, item, 2, act='save'), follow_redirects=False)
        r = int(saved.headers['location'].rsplit('/', 1)[1])
        assert get(c, u, r)['approval_status'] == 'draft'
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_more_than_can_be_requested_is_shown_on_the_cart_and_nothing_is_created(request_db, app_mod):
    c, u, _, path, item = request_db                                              # 10 on hand
    client, old = client_for(app_mod, path, u[2])
    try:
        bad = client.post('/supplies/requests/send', data=cart_data(client, item, 11, act='send'))
        assert bad.status_code == 422 and 'Review your request' in bad.text and 'Only 10' in bad.text and 'value="11"' in bad.text
        assert c.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_a_failed_submit_keeps_the_saved_draft_and_a_retry_updates_it(request_db, app_mod, monkeypatch):
    c, u, _, path, item = request_db
    client, old = client_for(app_mod, path, u[2])
    try:
        real = requests.submit
        monkeypatch.setattr(requests, 'submit', lambda *a, **k: (_ for _ in ()).throw(requests.Invalid('Synthetic refusal.')))
        page = client.post('/supplies/requests/send', data=cart_data(client, item, 3, act='send'))
        assert page.status_code == 422 and 'saved as a draft but was not sent: Synthetic refusal.' in page.text
        r = c.execute('SELECT id,approval_status FROM supply_request').fetchall()
        assert len(r) == 1 and r[0][1] == 'draft'
        monkeypatch.setattr(requests, 'submit', real)
        retry = {**cart_data(client, item, 5, act='send'), 'request_id': hidden(page.text, 'request_id'),
                 'revision': hidden(page.text, 'revision')}
        done = client.post('/supplies/requests/send', data=retry, follow_redirects=False)
        assert done.status_code == 303
        assert c.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 1
        assert get(c, u, r[0][0])['approval_status'] == 'submitted'
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old
