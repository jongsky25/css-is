"""Increment 1.3, rule R1: nobody can request more than is available to request."""
import pytest

import supplies_allocations as allocations
import supplies_requests as requests
from supplies_storage import Invalid, transaction
from tests.test_supplies import supplies_db, create, key
from tests.test_supplies_requests import request_db, draft, submit, get, fields, withdraw
from tests.test_supplies_approvals import approval_db, decide


def line(item, quantity):
    return {'lines': [{'item_id': item, 'requested_quantity': str(quantity)}]}


def test_over_limit_save_and_submit_are_refused_with_plain_message(request_db):
    c, u, _, _, item = request_db  # 10 on hand
    with pytest.raises(Invalid, match=r'Only 10 reams of Synthetic paper can be requested right now\.'):
        draft(c, u, item, **line(item, 11))
    assert c.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0
    r = draft(c, u, item, **line(item, 10))
    assert submit(c, u, r)['approval_status'] == 'submitted'


def test_zero_stock_and_unrecorded_items_cannot_be_requested(request_db):
    c, u, _, _, _ = request_db
    empty = create(c, u[1], code='NO-STOCK', description='Empty item')['id']
    assert allocations.requestable(c, empty) == 0
    with pytest.raises(Invalid, match='Empty item is out of stock'):
        draft(c, u, empty, **line(empty, 1))


def test_other_pending_requests_count_but_own_draft_does_not(request_db):
    c, u, _, _, item = request_db
    first = draft(c, u, item, **line(item, 6))
    assert allocations.requestable(c, item) == 10  # a draft holds nothing
    submit(c, u, first)
    assert allocations.requestable(c, item) == 4
    assert allocations.requestable(c, item, exclude_request_id=first) == 10
    with pytest.raises(Invalid, match='Only 4 reams'):
        requests.save_draft(c, u[3], fields(item, **line(item, 5)), operation_key=key())
    requests.save_draft(c, u[3], fields(item, **line(item, 4)), operation_key=key())


def test_withdrawn_and_approved_requests_free_or_reserve_correctly(approval_db):
    c, u, _, _, item = approval_db
    r = draft(c, u, item, **line(item, 6))
    submit(c, u, r)
    assert allocations.requestable(c, item) == 4
    withdraw(c, u, r)
    assert allocations.requestable(c, item) == 10
    r2 = draft(c, u, item, **line(item, 6))
    submit(c, u, r2)
    decide(c, u, r2)
    assert allocations.requestable(c, item) == 4  # now reserved instead of pending


def test_editing_own_draft_is_checked_against_others_only(request_db):
    c, u, _, _, item = request_db
    r = draft(c, u, item, **line(item, 10))
    saved = requests.save_draft(c, u[2], fields(item, **line(item, 9)), operation_key=key(),
                                request_id=r, expected_revision=get(c, u, r)['revision'])
    assert saved['id'] == r
    with pytest.raises(Invalid):
        requests.save_draft(c, u[2], fields(item, **line(item, 11)), operation_key=key(),
                            request_id=r, expected_revision=get(c, u, r)['revision'])


def test_submit_rechecks_when_stock_was_taken_after_the_draft_was_saved(request_db):
    c, u, _, _, item = request_db
    r = draft(c, u, item, **line(item, 8))
    other = requests.save_draft(c, u[3], fields(item, **line(item, 5)), operation_key=key())['id']
    requests.submit(c, u[3], other, expected_revision=1, operation_key=key())
    with pytest.raises(Invalid, match='Only 5 reams'):
        submit(c, u, r)
    assert get(c, u, r)['approval_status'] == 'draft'


def test_resubmitting_a_returned_request_is_rechecked(approval_db):
    c, u, _, _, item = approval_db
    r = draft(c, u, item, **line(item, 6))
    submit(c, u, r)
    from supplies_approvals import decide_request
    entry = get(c, u, r)
    decide_request(c, u[3], r, {'decision': 'returned', 'reason': 'Please check the quantity', 'lines': []},
                   expected_revision=entry['revision'], submitted_revision=entry['current_revision'], operation_key=key())
    taker = requests.save_draft(c, u[3], fields(item, **line(item, 8)), operation_key=key())['id']
    requests.submit(c, u[3], taker, expected_revision=1, operation_key=key())
    with pytest.raises(Invalid, match='Only 2 reams'):
        submit(c, u, r)


def test_mcp_in_transaction_paths_obey_the_same_limit(request_db):
    c, u, _, _, item = request_db
    with pytest.raises(Invalid):
        with transaction(c):
            requests.save_draft_in_transaction(c, u[2], fields(item, **line(item, 11)), operation_key=key())
    with transaction(c):
        r = requests.save_draft_in_transaction(c, u[2], fields(item, **line(item, 3)), operation_key=key())['id']
    c.execute('UPDATE supply_request_draft_line SET requested_quantity=11 WHERE request_id=?', (r,))
    c.commit()
    with pytest.raises(Invalid):
        with transaction(c):
            requests.submit_in_transaction(c, u[2], r, expected_revision=1, operation_key=key())


@pytest.mark.parametrize('available,critical,target,label', [
    (0, 5, 50, 'Out of stock'), (1, 5, 50, 'Limited'), (5, 5, 50, 'Limited'), (6, 5, 50, 'Available'),
    (10, 0, 50, 'Limited'), (11, 0, 50, 'Available'), (3, 0, None, 'Available'),
])
def test_badge(available, critical, target, label):
    assert allocations.badge(available, {'critical_level': critical, 'target_level': target}) == label
