"""S4.2 shared queue counts, submitted-unit scopes, filters and dashboard access."""
from urllib.parse import urlsplit,parse_qs

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_dashboard as views
import supplies_requests as requests
import supplies_approvals as approvals
import supplies_issues as issues
import supplies_notify as notify
from supplies_storage import Denied, Disabled, Invalid, Missing
from tests.test_supplies import supplies_db, key, create, hidden
from tests.test_supplies_requests import request_db, draft, submit, get, fields
from tests.test_supplies_approvals import approval_db, decide
from tests.test_supplies_backorders import ready, receipt
from tests.test_supplies_issues import issue, data as issue_data
from tests.test_supplies_acknowledgments import respond
from tests.test_supplies_corrections import correction
from tests.conftest import session_token


@pytest.fixture
def queue_db(approval_db):
    c,u,units,path,item=approval_db
    closed=ready(c,u,item,4);first=issue(c,u,closed,2)['id'];second=issue(c,u,closed,2)['id']
    pending=draft(c,u,item,purpose='Visible pending purpose');submit(c,u,pending)
    own_draft=draft(c,u,item,purpose='Private unsubmitted purpose')
    returned=draft(c,u,item,purpose='Returned editable purpose');submit(c,u,returned)
    approvals.decide_request(c,u[3],returned,{'decision':'returned','reason':'Synthetic correction'},expected_revision=2,submitted_revision=1,operation_key=key())
    outstanding=ready(c,u,item,8)
    return c,u,units,path,item,{'closed':closed,'pending':pending,'draft':own_draft,'returned':returned,'outstanding':outstanding,'first':first,'second':second}


def card_data(c,user):return views.dashboard(c,user)['cards']


def test_dashboard_cards_match_exact_authorized_filter_counts(queue_db):
    c,u,_,_,_,_=queue_db
    path_kind={'/supplies/requests':'requests','/supplies/approvals':'approvals','/supplies/issuance':'issuance',
               '/supplies/awaiting-stock':'shortages','/supplies/issues':'releases','/supplies/warnings':'warnings'}
    for user in u:
        for card in card_data(c,user):
            url=urlsplit(card['url']);params=parse_qs(url.query)
            if url.path=='/supplies/notices':
                assert card['count']==notify.list_notices(c,user,unread=True)['unread_count']
                continue
            result=views.queue(c,user,path_kind[url.path],state=params.get('status',[''])[0],mine=params.get('mine',[''])[0]=='1')
            key_name=views.QUEUE_META[path_kind[url.path]][0]
            assert result['total']==card['count']==len(result[key_name])
    own=views.queue(c,u[2],'requests',state='action')
    assert own['total']==2
    assert views.queue(c,u[3],'approvals')['total']==1
    assert views.queue(c,u[1],'issuance')['total']==1
    assert views.queue(c,u[2],'shortages')['total']==1


def test_own_private_drafts_do_not_enter_operational_or_other_unit_counts(queue_db):
    c,u,units,_,item,ids=queue_db
    # The approver's own submitted request is visible as owner but excluded from decisions.
    own=requests.save_draft(c,u[3],fields(item,purpose='Approver own request'),operation_key=key())['id']
    requests.submit(c,u[3],own,expected_revision=1,operation_key=key())
    c.execute('UPDATE resource_person SET org_unit_id=? WHERE id=?',(units[2],u[4]['rp_id']));c.commit()
    foreign=requests.save_draft(c,u[4],fields(item,purpose='SECRET foreign purpose'),operation_key=key())['id']
    requests.submit(c,u[4],foreign,expected_revision=1,operation_key=key())
    assert views.queue(c,u[3],'approvals')['total']==1
    assert views.queue(c,u[3],'approvals',query='SECRET')['total']==0
    with pytest.raises(Missing):requests.get_request(c,u[3],foreign)
    with pytest.raises(Missing):requests.get_request(c,u[1],ids['draft'])
    assert views.queue(c,u[0],'requests')['total']==0
    assert views.dashboard(c,u[0])['activities']==[]
    assert 'SECRET' not in str(views.dashboard(c,u[3]))


def test_returned_edits_do_not_move_submitted_read_scope_until_resubmission(queue_db):
    c,u,units,_,item,ids=queue_db;r=ids['returned']
    c.execute('UPDATE resource_person SET org_unit_id=? WHERE id=?',(units[2],u[2]['rp_id']));c.commit()
    requests.save_draft(c,u[2],fields(item,purpose='PRIVATE revised purpose'),request_id=r,expected_revision=3,operation_key=key())
    assert requests.get_request(c,u[3],r)['purpose']=='Returned editable purpose'
    assert views.queue(c,u[3],'approvals',query='PRIVATE')['total']==0
    requests.submit(c,u[2],r,expected_revision=4,operation_key=key())
    with pytest.raises(Missing):requests.get_request(c,u[3],r)
    assert views.queue(c,u[3],'approvals',query='PRIVATE')['total']==0


def test_assigned_recipient_counts_include_only_their_release_and_not_whole_request(queue_db):
    c,u,_,_,item,ids=queue_db
    release=issue(c,u,ids['outstanding'],1,fields=issue_data(c,u,ids['outstanding'],1,recipient_id=u[4]['id'],alternate_reason='Synthetic alternate'))['id']
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='request_approver'",(u[0]['id'],u[4]['id']));c.commit()
    mine=views.queue(c,u[4],'releases',state='pending',mine=True)
    assert mine['total']==1 and mine['releases'][0]['id']==release
    assert issues.get_issue(c,u[4],release)
    with pytest.raises(Missing):requests.get_request(c,u[4],ids['outstanding'])
    with pytest.raises(Missing):issues.get_issue(c,u[4],ids['first'])
    assert views.queue(c,u[4],'releases')['total']==1
    assert views.queue(c,u[4],'shortages')['total']==0


def test_counts_follow_acknowledgment_dispute_and_live_grant_revocation(queue_db):
    c,u,_,_,item,ids=queue_db
    assert views.queue(c,u[2],'releases',state='pending',mine=True)['total']==2
    respond(c,u,ids['first'])
    respond(c,u,ids['second'],'disputed',note='Synthetic discrepancy')
    assert views.queue(c,u[2],'releases',state='pending',mine=True)['total']==0
    assert views.queue(c,u[1],'releases',state='disputed')['total']==1
    assert 'Synthetic requester 2' in views.queue(c,u[1],'releases',state='disputed')['releases'][0]['next_action']
    grant=c.execute("SELECT id FROM supply_role_grant WHERE user_id=? AND role='request_approver' AND revoked_at IS NULL",(u[3]['id'],)).fetchone()[0]
    s.revoke_role(c,u[0],grant,expected_revision=1,operation_key=key())
    assert not any(card['url']=='/supplies/approvals' for card in card_data(c,u[3]))
    with pytest.raises(Denied):views.queue(c,u[3],'approvals')
    with pytest.raises(Missing):requests.get_request(c,u[3],ids['pending'])
    assert views.queue(c,u[3],'shortages')['total']==0


@pytest.mark.parametrize('kind,state',[('requests','action'),('requests','submitted'),('requests','outstanding'),
    ('approvals',''),('issuance',''),('shortages',''),('releases','pending'),('warnings','fully_reserved'),('activity','issue')])
def test_search_filters_counts_and_summaries_are_read_only(queue_db,kind,state):
    c,u,_,_,_,_=queue_db
    actor=u[3] if kind=='approvals' else u[1] if kind in ('issuance','warnings','activity') else u[2]
    tables=('supply_request','supply_stock_movement','supply_reservation','supply_notice','supply_alert_event','supply_operation')
    before={t:[tuple(row) for row in c.execute(f'SELECT * FROM {t}')] for t in tables}
    result=views.queue(c,actor,kind,state=state)
    assert result['total']>=1
    assert views.queue(c,actor,kind,state=state,query='NO MATCH')['total']==0
    assert views.queue(c,actor,kind,state=state,query="%' OR 1=1 --")['total']==0
    views.dashboard(c,actor)
    assert before=={t:[tuple(row) for row in c.execute(f'SELECT * FROM {t}')] for t in tables}


@pytest.mark.parametrize('kind',['requests','approvals','issuance','shortages','releases','warnings','activity'])
def test_invalid_page_search_and_filter_fail_cleanly(queue_db,kind):
    c,u,_,_,_,_=queue_db
    actor=u[3] if kind=='approvals' else u[1]
    for kw in ({'page':0},{'query':'x'*201},{'query':'bad\nquery'},{'state':'unknown'},{'limit':26}):
        with pytest.raises(Invalid):views.queue(c,actor,kind,**kw)


def test_pagination_preserves_search_state_and_personal_release_filter(approval_db):
    c,u,_,_,item=approval_db;receipt(c,u,item,30)
    for _ in range(26):
        r=ready(c,u,item,1);issue(c,u,r,1)
    first=views.queue(c,u[2],'releases',state='pending',mine=True,query='ISS-')
    second=views.queue(c,u[2],'releases',state='pending',mine=True,query='ISS-',page=2)
    assert first['total']==second['total']==26 and len(first['releases'])==25 and len(second['releases'])==1
    assert first['has_next'] and not second['has_next']
    assert next(card['count'] for card in card_data(c,u[2]) if card['title']=='My releases awaiting acknowledgment')==26
    params=parse_qs(urlsplit(first['next_url']).query)
    assert params=={'q':['ISS-'],'status':['pending'],'mine':['1'],'page':['2']}
    assert set(e['id'] for e in first['releases']).isdisjoint(e['id'] for e in second['releases'])


def test_next_person_labels_and_missing_approver_assignment(queue_db):
    c,u,_,_,_,ids=queue_db
    pending=views.queue(c,u[2],'requests',state='submitted')['requests'][0]
    assert 'Synthetic requester 3' in pending['next_action']
    assert 'Custodian' in views.queue(c,u[2],'requests',state='outstanding')['requests'][0]['next_action']
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE role='request_approver'",(u[0]['id'],));c.commit()
    assert views.queue(c,u[2],'requests',state='submitted')['requests'][0]['next_action']=='Administrator: assign a supply request approver'


def test_operational_activity_is_stock_reader_only_and_never_contains_costs(queue_db):
    c,u,_,_,_,_=queue_db
    for who in (0,2,3,4):
        with pytest.raises(Denied):views.queue(c,u[who],'activity')
        with pytest.raises(Denied):views.queue(c,u[who],'warnings')
        assert views.dashboard(c,u[who])['activities']==[]
    s.grant_role(c,u[0],u[4]['id'],'auditor',operation_key=key())
    assert views.queue(c,u[4],'activity')['total']==3
    assert all('unit_cost' not in row and 'supplier' not in row for row in views.queue(c,u[4],'activity')['activities'])
    assert not any(card['url']=='/supplies/issuance' for card in card_data(c,u[4]))


def test_disabled_dashboard_keeps_read_counts_and_blocks_business_posts(queue_db,app_mod):
    c,u,_,path,_,_=queue_db;old=app_mod.DB;app_mod.DB=path
    try:
        before=views.dashboard(c,u[1])['cards']
        c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
            dashboard=client.get('/supplies')
            assert dashboard.status_code==200 and 'Supplies overview' in dashboard.text and 'changes are paused' in dashboard.text
            assert 'New supply request</a>' not in dashboard.text
            assert views.dashboard(c,u[1])['cards']==before
            page=client.get('/supplies/issuance');assert page.status_code==200 and '/issues/new' not in page.text
            response=client.post('/supplies/allocations/refresh',data={'csrf':hidden(client.get('/supplies/warnings').text,'csrf'),'operation_key':key()})
            assert response.status_code==409
    finally:app_mod.DB=old


def test_http_dashboard_filters_and_queue_counts_match_and_scope_denies(queue_db,app_mod):
    c,u,_,path,_,_=queue_db;old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            for actor in (u[1],u[2],u[3]):
                client.cookies.set(auth.COOKIE_NAME,session_token(actor))
                assert client.get('/supplies').status_code==200
                for card in card_data(c,actor):
                    page=client.get(card['url']);assert page.status_code==200
                    if not card['url'].startswith('/supplies/notices'):
                        assert f'{card["count"]} matching ' in page.text
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            assert client.get('/supplies/activity').status_code==403
            assert client.get('/supplies/approvals').status_code==403
            assert client.get('/supplies/requests?q=%3Cscript%3E').status_code==200
            payload='<script>unique_test_only()</script>'
            escaped=client.get('/supplies/requests',params={'q':payload})
            assert payload not in escaped.text and '&lt;script&gt;unique_test_only()&lt;/script&gt;' in escaped.text
            assert client.get('/supplies/issues?status=unknown').status_code==422
            c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],));c.commit()
            assert client.get('/supplies',follow_redirects=False).status_code in (303,401,403)
    finally:app_mod.DB=old
