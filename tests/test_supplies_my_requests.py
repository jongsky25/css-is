"""Supplies 3.1: My requests as cards (needs-action section, Active / Completed / All, items, tracker)."""
import pytest
import supplies_dashboard as dashboard
import supplies_requests as requests
from tests.test_supplies import key, hidden, supplies_db  # noqa: F401
from tests.test_supplies_approvals import approval_db, decide  # noqa: F401
from tests.test_supplies_requests import request_db, draft, submit, get, withdraw  # noqa: F401
from tests.test_supplies_shop import client_for, second_item


def mixed(c, u, item):
    other = second_item(c, u, 9)
    d = draft(c, u, item, purpose='Still a draft')                                              # draft
    sub = draft(c, u, other, purpose='Waiting purpose', lines=[{'item_id': other, 'requested_quantity': '1'}])
    submit(c, u, sub)                                                                             # submitted
    ret = draft(c, u, item, purpose='Returned purpose', lines=[{'item_id': item, 'requested_quantity': '1'}])
    submit(c, u, ret)
    decide(c, u, ret, fields={'decision': 'returned', 'reason': 'Add a date'})                    # returned
    rej = draft(c, u, other, purpose='Rejected purpose', lines=[{'item_id': other, 'requested_quantity': '1'}])
    submit(c, u, rej)
    decide(c, u, rej, fields={'decision': 'rejected', 'reason': 'Not needed'})                    # rejected
    return d, sub, ret, rej


def ids(data):
    return {e['id'] for e in data['requests']}


@pytest.mark.usefixtures("unlimited_requests")
def test_the_three_views_split_requests_by_who_can_move_them_forward(approval_db):
    c, u, _, _, item = approval_db
    d, sub, ret, rej = mixed(c, u, item)
    q = lambda state: ids(requests.my_requests(c, u[2], state=state))
    assert q('needs_action') == {d, ret}
    assert q('active') == {sub}
    assert q('completed') == {rej}
    assert q('') == {d, sub, ret, rej}
    assert q('action') == {d, ret}                                                                # the dashboard's old links still work


@pytest.mark.usefixtures("unlimited_requests")
def test_the_page_leads_with_what_needs_action_and_shows_items_and_progress(approval_db, app_mod):
    c, u, _, path, item = approval_db
    d, sub, ret, rej = mixed(c, u, item)
    client, old = client_for(app_mod, path, u[2])
    try:
        page = client.get('/supplies/requests').text                                              # opens on Active
        assert page.index('Needs your action') < page.index('class="req-tabs"')
        assert 'Still a draft' not in page and 'Draft request' in page and 'Fix and resend' in page and 'Review and send' in page
        assert f'/supplies/requests/{d}/edit' in page and f'/supplies/requests/{ret}/edit' in page
        assert page.count('class="req-track"') == 1 and 'Waiting for' in page                       # only the sent one has a tracker
        assert 'class="req-pic"' in page or 'class="req-pic" style' in page
        assert page.count(f'href="/supplies/requests/{sub}"') == 1                                # not repeated under Active
        done = client.get('/supplies/requests?status=completed').text
        assert 'Not approved' in done and 'Needs your action' in done and 'Waiting for' not in done
        every = client.get('/supplies/requests?status=all').text
        assert 'Not approved' in every and 'Waiting for' in every and every.count(f'href="/supplies/requests/{ret}"') == 1
        old_link = client.get('/supplies/requests?status=action').text
        assert 'Needs your action' not in old_link and 'Fix and resend' in old_link and 'Waiting for' not in old_link
        assert 'matching request' in page
        assert 'nothing in progress' not in page
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_a_requester_with_nothing_sees_a_plain_message(request_db, app_mod):
    c, u, _, path, _ = request_db
    client, old = client_for(app_mod, path, u[2])
    try:
        assert 'You have nothing in progress.' in client.get('/supplies/requests').text
        assert 'no supply requests yet' in client.get('/supplies/requests?status=all').text
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old
