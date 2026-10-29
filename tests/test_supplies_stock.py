"""S1.2 stock transactions, receipts, access boundaries and immutable evidence."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_stock as stock
from supplies_storage import Conflict, Denied, Disabled, Invalid
from tests.test_supplies import supplies_db, setup_catalog, create, fields, key, hidden
from tests.conftest import session_token


def opening(c, user, item, quantity='10', **changes):
    return stock.post_opening(c, user, item['id'], {'quantity': quantity, 'effective_date': '2026-10-19',
        'reason': 'Synthetic reviewed count', **changes}, expected_revision=item['revision'], operation_key=key())


def receipt(item, quantity='5', **changes):
    return {'supplier': 'Synthetic Supplier', 'effective_date': '2026-10-19', 'dr_number': 'DR-TEST-1',
            'apr_number': 'APR-TEST-1', 'procurement_mode': 'Synthetic procurement', 'note': 'Accepted delivery',
            'lines': [{'item_id': item['id'], 'expected_revision': item['revision'],
                       'accepted_quantity': quantity, 'unit_cost': '2.1250', 'expiry_date': '2027-01-01'}], **changes}


def receive(c, user, item, quantity='5', **changes):
    return stock.post_receipt(c, user, receipt(item, quantity, **changes), operation_key=key())


def test_opening_plus_receipt_and_identical_retry(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    assert stock.stock_totals(c, u[2], item['id']) == {'on_hand': 0, 'recorded': False, 'movement_count': 0}
    op = key()
    data = {'quantity': '10', 'effective_date': '2026-10-19', 'reason': 'Reviewed count'}
    original = stock.post_opening(c, u[1], item['id'], data, expected_revision=1, operation_key=op)
    assert stock.post_opening(c, u[1], item['id'], data, expected_revision=1, operation_key=op) == original
    with pytest.raises(Conflict):
        stock.post_opening(c, u[1], item['id'], {**data, 'quantity': '11'}, expected_revision=1, operation_key=op)
    with pytest.raises(Conflict, match='empty item ledger'):
        opening(c, u[1], item)
    receipt_key = key()
    result = stock.post_receipt(c, u[1], receipt(item), operation_key=receipt_key)
    assert stock.post_receipt(c, u[1], receipt(item), operation_key=receipt_key) == result
    assert stock.stock_totals(c, u[2], item['id'])['on_hand'] == 15
    card = stock.stock_card(c, u[1], item['id'])
    assert [m['balance'] for m in card['movements']] == [10, 15]
    assert result['lines'][0]['unit_cost'] == '2.1250'
    assert result['lines'][0]['expiry_date'] == '2027-01-01'
    assert result['supplier'] == 'Synthetic Supplier' and result['dr_number'] == 'DR-TEST-1'
    assert stock.list_receipts(c, u[1])['receipts'][0]['receipt_number'] == result['receipt_number']
    assert c.execute("SELECT COUNT(*) FROM supply_event WHERE action IN ('opening_post','receipt_post')").fetchone()[0] == 2
    before = {t: c.execute(f'SELECT * FROM {t} ORDER BY id').fetchall()
              for t in ('supply_receipt', 'supply_receipt_line', 'supply_stock_movement')}
    st.init_db(c)
    st.init_db(c)
    assert before == {t: c.execute(f'SELECT * FROM {t} ORDER BY id').fetchall() for t in before}


def test_receipt_first_blocks_opening_and_zero_opening_locks_unit(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    receive(c, u[1], item)
    with pytest.raises(Conflict, match='empty item ledger'):
        opening(c, u[1], item)
    other = create(c, u[1], code='ZERO')
    opening(c, u[1], other, quantity='0')
    assert stock.stock_totals(c, u[2], other['id'])['recorded']
    with pytest.raises(Conflict, match='unit is fixed'):
        s.update_item(c, u[1], other['id'], fields(code='ZERO', unit='Piece'), expected_revision=1, operation_key=key())


def test_multiline_costs_snapshots_and_backdating(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    opening(c, u[1], item, effective_date='2026-10-19')
    data = receipt(item)
    data['effective_date'] = '2026-10-01'
    data['lines'].append({**data['lines'][0], 'accepted_quantity': '2', 'unit_cost': '', 'expiry_date': ''})
    result = stock.post_receipt(c, u[1], data, operation_key=key())
    assert [line['unit_cost'] for line in result['lines']] == ['2.1250', None]
    s.update_item(c, u[1], item['id'], fields(description='Renamed after delivery'), expected_revision=1, operation_key=key())
    assert stock.get_receipt(c, u[1], result['id'])['lines'][0]['description_snapshot'] == 'Synthetic paper'
    card = stock.stock_card(c, u[1], item['id'])
    assert [m['balance'] for m in card['movements']] == [10, 15, 17]
    assert [m['effective_date'] for m in card['movements']] == ['2026-10-19', '2026-10-01', '2026-10-01']
    assert all(m['description_snapshot'] == 'Synthetic paper' for m in card['movements'])
    catalog_item = s.catalog(c, u[2])['items'][0]
    assert catalog_item['on_hand'] == 17 and catalog_item['movement_count'] == 3


def test_large_stock_totals_and_known_zero_cost(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    opening(c, u[1], item, quantity='2147483647')
    data = receipt(item)
    data['lines'][0]['unit_cost'] = '0'
    result = stock.post_receipt(c, u[1], data, operation_key=key())
    assert result['lines'][0]['unit_cost'] == '0.0000'
    assert stock.stock_totals(c, u[1], item['id'])['on_hand'] == 2147483652


@pytest.mark.parametrize('value', ['-1', '1.5', True, 1.0, '2147483648', 'NaN'])
def test_invalid_openings_have_no_posted_side_effect(supplies_db, value):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    with pytest.raises(Invalid):
        opening(c, u[1], item, quantity=value)
    assert not stock.stock_totals(c, u[1], item['id'])['recorded']


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', '1e2', '1.00001', '1000000000', 2.5, False])
def test_invalid_receipt_cost_rolls_back(supplies_db, value):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    data = receipt(item)
    data['lines'][0]['unit_cost'] = value
    with pytest.raises(Invalid):
        stock.post_receipt(c, u[1], data, operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_receipt').fetchone()[0] == 0
    assert not stock.stock_totals(c, u[1], item['id'])['recorded']


@pytest.mark.parametrize('value', ['2026-02-30', '20261019', '', '2026-10-21'])
def test_bad_or_future_effective_dates_rejected(supplies_db, value):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    with pytest.raises(Invalid):
        opening(c, u[1], item, effective_date=value)
    with pytest.raises(Invalid):
        receive(c, u[1], item, effective_date=value)


def test_stale_item_or_invalid_second_line_aborts_whole_receipt(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    first = create(c, u[1])
    second = create(c, u[1], code='SECOND')
    data = receipt(first)
    data['lines'].append({**data['lines'][0], 'item_id': second['id']})
    s.update_item(c, u[1], second['id'], fields(code='SECOND', unit='Pack'), expected_revision=1, operation_key=key())
    with pytest.raises(Conflict, match='confirm its unit'):
        stock.post_receipt(c, u[1], data, operation_key=key())
    data['lines'][1]['expected_revision'] = 2
    data['lines'][1]['accepted_quantity'] = '0'
    with pytest.raises(Invalid):
        stock.post_receipt(c, u[1], data, operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_receipt').fetchone()[0] == 0
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0] == 0


def test_audit_failure_and_aggregate_overflow_roll_back_every_record(supplies_db, monkeypatch):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    count = c.execute('SELECT COUNT(*) FROM supply_operation').fetchone()[0]
    def fail(*args, **kwargs):
        raise RuntimeError('Synthetic failed audit')
    with monkeypatch.context() as patch:
        patch.setattr(st, 'audit', fail)
        with pytest.raises(RuntimeError, match='failed audit'):
            receive(c, u[1], item)
        with pytest.raises(RuntimeError, match='failed audit'):
            opening(c, u[1], item)
    with monkeypatch.context() as patch:
        patch.setattr(stock, '_totals', lambda *args: {'on_hand': stock.MAX_TOTAL, 'recorded': True, 'movement_count': 1})
        with pytest.raises(Invalid, match='supported range'):
            receive(c, u[1], item)
    for table in ('supply_receipt', 'supply_receipt_line', 'supply_stock_movement'):
        assert c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert c.execute('SELECT COUNT(*) FROM supply_operation').fetchone()[0] == count
    assert not c.in_transaction


def test_current_permissions_privacy_disabled_and_inactive_items(supplies_db):
    c, u, _, _ = supplies_db
    grant = setup_catalog(c, u)
    item = create(c, u[1])
    result = receive(c, u[1], item)
    s.grant_role(c, u[0], u[3]['id'], 'auditor', operation_key=key())
    assert stock.get_receipt(c, u[3], result['id'])['supplier'] == 'Synthetic Supplier'
    with pytest.raises(Denied):
        receive(c, u[3], item)
    for who in (u[0], u[2]):
        with pytest.raises(Denied):
            receive(c, who, item)
        with pytest.raises(Denied):
            stock.get_receipt(c, who, result['id'])
        with pytest.raises(Denied):
            stock.stock_card(c, who, item['id'])
    assert stock.stock_totals(c, u[2], item['id'])['on_hand'] == 5
    s.set_enabled(c, u[0], '0', expected_revision=1, operation_key=key())
    assert stock.stock_card(c, u[1], item['id'])['on_hand'] == 5
    with pytest.raises(Disabled):
        receive(c, u[1], item)
    s.set_enabled(c, u[0], '1', expected_revision=2, operation_key=key())
    s.deactivate_item(c, u[1], item['id'], expected_revision=1, operation_key=key(), reason='Retired')
    with pytest.raises(Conflict, match='inactive'):
        receive(c, u[1], item)
    s.revoke_role(c, u[0], grant['id'], expected_revision=1, operation_key=key())
    with pytest.raises(Denied):
        stock.stock_card(c, u[1], item['id'])


def test_posted_receipt_and_movement_immutability(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    receive(c, u[1], item)
    for table, column in [('supply_receipt', 'supplier'), ('supply_receipt_line', 'unit_cost'),
                          ('supply_stock_movement', 'reason')]:
        for sql in (f'DELETE FROM {table}', f"UPDATE {table} SET {column}='tampered'"):
            with pytest.raises(sqlite3.IntegrityError, match='immutable'):
                c.execute(sql)
            c.rollback()
    assert stock.stock_card(c, u[1], item['id'])['on_hand'] == 5
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_independent_connections_serialize_openings_and_receipt_retries(supplies_db):
    c, u, _, path = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    barrier = threading.Barrier(2)
    def post_opening():
        db = st.connect(path)
        try:
            barrier.wait(timeout=5)
            try:
                return opening(db, u[1], item)
            except Conflict:
                return 'conflict'
        finally:
            db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post_opening(), range(2)))
    assert results.count('conflict') == 1
    assert stock.stock_totals(c, u[1], item['id'])['on_hand'] == 10
    shared_key = key()
    barrier = threading.Barrier(2)
    def post_receipt():
        db = st.connect(path)
        try:
            barrier.wait(timeout=5)
            return stock.post_receipt(db, u[1], receipt(item), operation_key=shared_key)
        finally:
            db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post_receipt(), range(2)))
    assert results[0] == results[1]
    assert stock.stock_totals(c, u[1], item['id'])['on_hand'] == 15
    assert c.execute('SELECT COUNT(*) FROM supply_receipt').fetchone()[0] == 1


def test_stock_card_running_balances_continue_across_pages(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    opening(c, u[1], item)
    for _ in range(51):
        receive(c, u[1], item, quantity='1')
    first = stock.stock_card(c, u[1], item['id'])
    second = stock.stock_card(c, u[1], item['id'], page=2)
    assert first['has_next'] and not second['has_next']
    assert [m['balance'] for m in second['movements']] == [60, 61]
    assert len(stock.list_receipts(c, u[1])['receipts']) == 50
    assert stock.list_receipts(c, u[1], page=2)['receipts'][0]['id'] == 1


def test_opening_receipt_http_and_cost_privacy(app_mod, supplies_db):
    c, u, _, path = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    old_db = app_mod.DB
    app_mod.DB = path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME, session_token(u[1]))
            target = f"/supplies/items/{item['id']}"
            form = client.get(target)
            token = hidden(form.text, 'csrf')
            data = {'csrf': token, 'operation_key': key(), 'revision': 1, 'quantity': '10',
                    'effective_date': '2026-10-19', 'reason': 'Synthetic physical count'}
            assert client.post(target + '/opening', data={**data, 'csrf': 'invalid'}).status_code == 403
            assert client.post(target + '/opening', data=data, follow_redirects=False).status_code == 303
            assert client.post(target + '/opening', data=data, follow_redirects=False).status_code == 303
            form = client.get('/supplies/receipts/new')
            assert form.status_code == 200
            data = {'csrf': token, 'operation_key': key(), 'supplier': 'Confidential Supplier',
                    'effective_date': '2026-10-19', 'item_choice_0': f"{item['id']}:1",
                    'quantity_0': '5', 'unit_cost_0': '123.4567', 'expiry_date_0': '2027-01-01'}
            assert client.post('/supplies/receipts', data=data, headers={'Origin': 'https://foreign.example'}).status_code == 403
            posted = client.post('/supplies/receipts', data=data, follow_redirects=False)
            assert posted.status_code == 303
            detail_url = posted.headers['location']
            detail = client.get(detail_url)
            assert '123.4567' in detail.text and 'Confidential Supplier' in detail.text
            assert client.get('/supplies/receipts').status_code == 200
            assert client.post('/supplies/receipts', data=data, follow_redirects=False).headers['location'] == detail_url
            invalid = client.post('/supplies/receipts', data={**data, 'quantity_0': '0', 'operation_key': key()})
            assert invalid.status_code == 422 and 'Confidential Supplier' in invalid.text
            assert stock.stock_totals(c, u[1], item['id'])['on_hand'] == 15
            client.cookies.set(auth.COOKIE_NAME, session_token(u[2]))
            staff_detail = client.get(target, follow_redirects=False)                  # Supplies 4.1: staff are sent to the request grid
            assert staff_detail.status_code == 303 and staff_detail.headers['location'] == '/supplies/requests/new'
            assert 'Confidential Supplier' not in staff_detail.text and '123.4567' not in staff_detail.text
            for url in ('/supplies/receipts', '/supplies/receipts/new', detail_url):
                assert client.get(url).status_code == 403
            assert 'Confidential Supplier' not in client.get('/supplies/items').text
    finally:
        app_mod.DB = old_db
