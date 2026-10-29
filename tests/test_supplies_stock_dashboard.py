"""Stock charts/list reuse inventory rules, exact drill-downs and current grants."""
from urllib.parse import urlsplit,parse_qs

import pytest
import supplies_grid as grid
import supplies_stock_dashboard as dashboard
from supplies_storage import Denied,Invalid
from tests.test_supplies import supplies_db,setup_catalog,create,key,reader
from tests.test_supplies_stock import opening,receive
from tests.test_supplies_requests import request_db
from tests.test_supplies_approvals import approval_db
from tests.test_supplies_backorders import ready


def params(href):return {k:v[0] for k,v in parse_qs(urlsplit(href).query,keep_blank_values=True).items()}


def test_counts_threshold_unknown_zero_unit_scope_and_exact_links(supplies_db):
    c,u,_,_=supplies_db;setup_catalog(c,u);reader(c,u)
    for index,quantity in enumerate((None,'0','4','5','12')):
        item=create(c,u[1],code=f'CHART-{index}',unit='Ream' if index<4 else 'Box')
        if quantity is not None:opening(c,u[1],item,quantity=quantity)
    zero=create(c,u[1],code='ZERO-LEVEL',critical_level='0',target_level='')
    opening(c,u[1],zero,quantity='0')
    inactive=create(c,u[1],code='INACTIVE',unit='Secret unit')
    opening(c,u[1],inactive,quantity='1')
    c.execute('UPDATE supply_item SET active=0 WHERE id=?',(inactive['id'],));c.commit()
    before=c.total_changes
    report=dashboard.report(c,u[2],{})
    assert report['total']==6 and report['low_count']==2
    assert {r['key']:r['count'] for r in report['physical']}=={'unrecorded':1,'inactive':0,'out_of_stock':2,'critical':1,'normal':2}
    assert [r['code'] for r in report['low_items']]==['CHART-1','CHART-2']
    assert report['low_items'][0]['on_hand']=='0' and report['low_items'][0]['target_level']=='20'
    assert c.total_changes==before
    for scope in ({},{'unit':'Ream'},{'q':'CHART-'},{'active':'all'},{'active':'inactive'}):
        user=u[1] if scope.get('active') else u[2]
        data=dashboard.report(c,user,scope)
        assert data['total']==grid.page(c,user,scope)['last_row']
        for field in ('physical','availability'):
            assert sum(row['count'] for row in data[field])==data['total']
            for row in data[field]:
                if row['count']:
                    assert grid.page(c,user,params(row['href']))['last_row']==row['count']
                    assert grid.export_csv(c,user,params(row['href']))[1]==row['count']
    assert dashboard.report(c,u[2],{'unit':'Secret unit'})['total']==0
    assert dashboard.report(c,u[2],{'q':'not found','page':'999'})['page']==1


def test_low_list_all_pages_search_and_live_inactive_authority(supplies_db):
    c,u,_,_=supplies_db;grant=setup_catalog(c,u);reader(c,u)
    for index in range(31):
        item=create(c,u[1],code=f'LOW-{index:03}')
        opening(c,u[1],item,quantity='2')
    data=dashboard.report(c,u[2],{'q':'LOW-'})
    second=dashboard.report(c,u[2],params(data['next']))
    assert data['low_count']==31 and len(data['low_items'])==30 and len(second['low_items'])==1
    assert second['low_items'][0]['code']=='LOW-030'
    with pytest.raises(Denied):dashboard.report(c,u[0],{'active':'all'})
    assert dashboard.report(c,u[1],{'active':'all'})['total']==31
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-24',revoked_by=? WHERE id=?",(u[0]['id'],grant['id']));c.commit()
    with pytest.raises(Denied):dashboard.report(c,u[1],{'active':'all'})
    with pytest.raises(Denied):dashboard.report(c,u[1],{})                         # Supplies 4.2: no grant left, no stock numbers
    assert dashboard.report(c,u[2],{})['total']==31                                # an approver still reads the active items
    with pytest.raises(Denied):dashboard.report(c,u[2],{'active':'all'})
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],));c.commit()
    with pytest.raises(Denied):dashboard.report(c,u[2],{})


def test_reservations_change_availability_not_physical_counts(approval_db):
    c,u,_,_,identifier=approval_db
    ready(c,u,identifier,'10')
    report=dashboard.report(c,u[3],{})
    assert next(r['count'] for r in report['availability'] if r['key']=='fully_reserved')==1
    assert next(r['count'] for r in report['physical'] if r['key']=='normal')==1
    assert report['low_count']==0
    import supplies
    receive(c,u[1],supplies.get_item(c,u[1],identifier),quantity='5')
    ready(c,u,identifier,'3')
    changed=dashboard.report(c,u[3],{})
    assert next(r['count'] for r in changed['availability'] if r['key']=='low_available')==1
    assert changed['low_count']==0


@pytest.mark.parametrize('invalid',[{'page':'0'},{'page':'-1'},{'page':'1000001'},{'q':'x'*201},
    {'active':'bad'},{'unit':None},{'active':False}])
def test_invalid_dashboard_scope(supplies_db,invalid):
    c,u,_,_=supplies_db
    with pytest.raises(Invalid):dashboard.report(c,u[2],invalid)
