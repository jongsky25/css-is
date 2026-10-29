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


# ---- Supplies 3.2: the owner's request page ----

@pytest.mark.usefixtures("unlimited_requests")
def test_the_owner_sees_where_the_request_is_and_the_old_detail_sits_under_full_details(approval_db, app_mod):
    c, u, _, path, item = approval_db
    sub = draft(c, u, item, lines=[{'item_id': item, 'requested_quantity': '3'}])
    submit(c, u, sub)
    client, old = client_for(app_mod, path, u[2])
    try:
        page = client.get(f'/supplies/requests/{sub}').text
        assert 'class="req-head' in page and 'Waiting for ' in page and 'asked 3' in page and 'approved' not in page.split('Full details')[0]
        assert page.count('class="req-track"') == 1 and 'Print the request form' in page and f'/supplies/requests/{sub}/again' in page
        head, details = page.split('Full details', 1)
        assert 'Withdraw request' in head and 'Withdraw request' not in details                    # the action is in context, once
        assert 'Submitted item snapshots' in details and 'Request timeline' in details
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


@pytest.mark.usefixtures("unlimited_requests")
def test_draft_returned_and_approved_requests_show_their_own_action_and_quantities(approval_db, app_mod):
    c, u, _, path, item = approval_db
    d = draft(c, u, item)
    ret = draft(c, u, item, lines=[{'item_id': item, 'requested_quantity': '1'}])
    submit(c, u, ret)
    decide(c, u, ret, fields={'decision': 'returned', 'reason': 'Add a date'})
    ok = draft(c, u, item, lines=[{'item_id': item, 'requested_quantity': '2'}])
    submit(c, u, ok)
    decide(c, u, ok, quantity=2)
    client, old = client_for(app_mod, path, u[2])
    try:
        assert 'Review and send' in client.get(f'/supplies/requests/{d}').text
        back = client.get(f'/supplies/requests/{ret}').text
        assert 'Fix and resend' in back and f'/supplies/requests/{ret}/edit' in back
        done = client.get(f'/supplies/requests/{ok}').text
        assert 'asked 2 · approved 2 · received 0' in done and done.count('class="req-track"') == 1
        assert 'Ready for pickup' in done or 'Waiting for stock' in done or 'Approved' in done
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


@pytest.mark.usefixtures("unlimited_requests")
def test_the_approver_sees_the_same_page_as_before(approval_db, app_mod):
    c, u, _, path, item = approval_db
    sub = draft(c, u, item)
    submit(c, u, sub)
    client, old = client_for(app_mod, path, u[3])
    try:
        page = client.get(f'/supplies/requests/{sub}').text
        assert 'req-head' not in page and 'Full details' not in page and 'class="req-track"' not in page
        assert 'Record decision' in page and 'Submitted item snapshots' in page and 'Request timeline' in page
        assert 'Request again' not in page and 'Withdraw request' not in page
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


# ---- Supplies 3.3: one-tap receipt confirmation ----

from tests.test_supplies_acknowledgments import released  # noqa: E402,F401
import supplies_issues as issues  # noqa: E402


def ack_status(c, u, issue_id):
    return issues.get_issue(c, u[1], issue_id)['acknowledgment']['status']


def test_the_release_page_has_two_plain_answers_for_the_recipient(released, app_mod):
    c, u, _, path, _, r, first, second = released
    client, old = client_for(app_mod, path, u[2])
    try:
        page = client.get(f'/supplies/issues/{first}').text
        assert 'Yes, I received it' in page and 'Report a problem' in page and '<select id="ack-status"' not in page
        data = {'csrf': hidden(page, 'csrf'), 'operation_key': key(), 'revision': '0', 'status': 'acknowledged'}
        done = client.post(f'/supplies/issues/{first}/acknowledge', data=data, follow_redirects=False)
        assert done.status_code == 303 and done.headers['location'] == f'/supplies/issues/{first}'
        assert ack_status(c, u, first) == 'acknowledged'
        after = client.get(f'/supplies/issues/{first}').text
        assert 'Yes, I received it' not in after and 'Report a problem' in after             # a problem can still be raised
        # a problem needs its reason; then the recipient resolves it with an explanation
        late = {'csrf': hidden(after, 'csrf'), 'operation_key': key(), 'revision': '1', 'status': 'disputed', 'note': ''}
        assert client.post(f'/supplies/issues/{first}/acknowledge', data=late).status_code == 422
        client.post(f'/supplies/issues/{first}/acknowledge', data={**late, 'note': 'Two reams were damaged'})
        assert ack_status(c, u, first) == 'disputed'
        disputed = client.get(f'/supplies/issues/{first}').text
        assert 'sorted out' in disputed and 'Report a problem' not in disputed
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_the_request_page_confirms_receipt_in_one_tap_and_comes_back_to_itself(released, app_mod):
    c, u, _, path, _, r, first, second = released
    client, old = client_for(app_mod, path, u[2])
    try:
        page = client.get(f'/supplies/requests/{r}').text
        head = page.split('Full details')[0]
        assert 'Please confirm receipt' in head and 'Yes, I received ISS-2026-00001' in head and 'Report a problem with ISS-2026-00002' in head
        data = {'csrf': hidden(page, 'csrf'), 'operation_key': key(), 'revision': '0', 'status': 'acknowledged',
                'back': f'/supplies/requests/{r}'}
        done = client.post(f'/supplies/issues/{first}/acknowledge', data=data, follow_redirects=False)
        assert done.headers['location'] == f'/supplies/requests/{r}' and ack_status(c, u, first) == 'acknowledged'
        after = client.get(f'/supplies/requests/{r}').text.split('Full details')[0]
        assert 'Yes, I received ISS-2026-00001' not in after and 'Yes, I received ISS-2026-00002' in after
        outside = client.post(f'/supplies/issues/{second}/acknowledge', data={**data, 'operation_key': key(), 'back': 'https://evil.example/x'},
                              follow_redirects=False)
        assert outside.headers['location'] == f'/supplies/issues/{second}'                  # only the request page is allowed back
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


# ---- Supplies 3.4: the Supplies home ----

@pytest.mark.usefixtures("unlimited_requests")
def test_the_home_leads_with_one_button_what_needs_action_and_the_latest_requests(approval_db, app_mod):
    c, u, _, path, item = approval_db
    d, sub, ret, rej = mixed(c, u, item)
    client, old = client_for(app_mod, path, u[2])
    try:
        page = client.get('/supplies').text
        assert 'supply-big-button' in page and '>Request supplies<' in page and 'Overview' not in page.split('<h1>')[1].split('</h1>')[0]
        assert page.index('Needs your action') < page.index('Your latest requests')
        assert 'Review and send' in page and 'Fix and resend' in page
        assert f'href="/supplies/requests/{sub}"' in page and f'href="/supplies/requests/{rej}"' in page
        assert page.count(f'href="/supplies/requests/{d}"') == 1                                  # not repeated under latest
        assert page.count('class="req-track"') == 1 and 'See all my requests' in page
        assert 'supply-dashboard-grid' not in page                                              # no role cards for a requester
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_management_users_keep_their_role_cards_and_get_their_own_requests_too(approval_db, app_mod):
    c, u, _, path, item = approval_db
    draft(c, u, item, purpose='Custodian draft')
    client, old = client_for(app_mod, path, u[3])                                                 # an approver
    try:
        page = client.get('/supplies').text
        assert 'supply-dashboard-grid' in page and 'Request supplies' in page and 'Your latest requests' in page
        assert 'Supplies overview' in page
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_a_requester_with_no_requests_sees_the_button_and_a_plain_message(request_db, app_mod):
    c, u, _, path, _ = request_db
    client, old = client_for(app_mod, path, u[2])
    try:
        page = client.get('/supplies').text
        assert 'Request supplies' in page and 'You have not made a supply request yet.' in page and 'Needs your action' not in page
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


# ---- Supplies 4.1: requester-only users are sent away from the management pages ----

def test_a_requester_is_sent_from_the_management_pages_to_their_own(released, app_mod):
    c, u, _, path, _, r, first, second = released
    client, old = client_for(app_mod, path, u[2])
    try:
        go = lambda url: client.get(url, follow_redirects=False)
        sent = go('/supplies/items?q=bond+paper')
        assert sent.status_code == 303 and sent.headers['location'] == '/supplies/requests/new?q=bond+paper'
        assert go('/supplies/items').headers['location'] == '/supplies/requests/new'
        assert go('/supplies/items/1').headers['location'] == '/supplies/requests/new'
        assert go('/supplies/issues?mine=1&status=pending').headers['location'] == '/supplies/requests'
        assert go('/supplies/awaiting-stock').headers['location'] == '/supplies/requests?status=active'
        assert go(f'/supplies/issues/{first}').status_code == 200                                # a link from an email still works
        assert go(f'/supplies/requests/{r}').status_code == 200
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_people_who_manage_supplies_keep_those_pages(released, app_mod):
    c, u, _, path, _, r, first, second = released
    for who in (u[1], u[3]):                                                                      # custodian and approver
        client, old = client_for(app_mod, path, who)
        try:
            for url in ('/supplies/items', '/supplies/issues', '/supplies/awaiting-stock'):
                assert client.get(url, follow_redirects=False).status_code == 200, (who['username'], url)
        finally:
            client.__exit__(None, None, None)
            app_mod.DB = old


# ---- Supplies 4.2: stock numbers for the supply office, auditors and approvers only ----

def test_a_requester_cannot_read_stock_numbers_anywhere(approval_db, app_mod):
    c, u, _, path, item = approval_db
    import supplies_grid as grid
    import supplies_stock_dashboard as dash
    from supplies_storage import Denied
    for call in (lambda: grid.page(c, u[2], {}), lambda: grid.export_csv(c, u[2], {}), lambda: dash.report(c, u[2], {})):
        with pytest.raises(Denied):
            call()
    client, old = client_for(app_mod, path, u[2])
    try:
        sent = client.get('/supplies/stock-dashboard?q=paper', follow_redirects=False)
        assert sent.status_code == 303 and sent.headers['location'] == '/supplies/requests/new'
        for url in ('/supplies/inventory-data', '/supplies/inventory-export.csv',
                    '/supplies/stock-dashboard/presentation-data', '/supplies/stock-dashboard/export.pdf'):
            assert client.get(url).status_code == 403, url
        grid_page = client.get('/supplies/requests/new').text
        assert 'on hand' not in grid_page.lower() and 'shop-badge' in grid_page                 # badges, not quantities
    finally:
        client.__exit__(None, None, None)
        app_mod.DB = old


def test_the_supply_office_auditors_and_approvers_keep_the_stock_numbers(approval_db, app_mod):
    c, u, units, path, item = approval_db
    import supplies as s
    s.grant_role(c, u[0], u[4]['id'], 'auditor', operation_key=key())
    for who in (u[0], u[1], u[3], u[4]):                                                     # admin, custodian, approver, auditor
        client, old = client_for(app_mod, path, who)
        try:
            assert client.get('/supplies/inventory-data').status_code == 200, who['username']
            assert client.get('/supplies/stock-dashboard', follow_redirects=False).status_code == 200, who['username']
        finally:
            client.__exit__(None, None, None)
            app_mod.DB = old
