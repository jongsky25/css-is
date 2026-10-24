"""Fresh, complete and bounded authorized stock snapshots for presentation exports."""
import pytest
import supplies_stock_dashboard as dashboard
from supplies_storage import Invalid,Denied
from tests.test_supplies import supplies_db,setup_catalog,create
from tests.test_supplies_stock import opening


def test_presentation_all_pages_exact_quantities_and_current_authority(supplies_db):
    c,u,_,_=supplies_db;grant=setup_catalog(c,u)
    for index in range(31):
        item=create(c,u[1],code=f'EXPORT-{index:03}',target_level='')
        opening(c,u[1],item,quantity='2')
    unknown=create(c,u[1],code='UNKNOWN')
    before=c.total_changes
    data=dashboard.report(c,u[2],{'q':'EXPORT-','page':'2'},presentation=True)
    assert data['low_count']==31 and len(data['low_items'])==31 and data['total']==31
    assert data['low_items'][0]['code']=='EXPORT-000' and data['low_items'][-1]['code']=='EXPORT-030'
    assert data['low_items'][0]['on_hand']=='2' and data['low_items'][0]['target_level'] is None
    assert c.total_changes==before
    assert dashboard.report(c,u[2],{'q':'UNKNOWN'},presentation=True)['low_items']==[]
    assert dashboard.report(c,u[1],{'active':'all'},presentation=True)['total']==32
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-24',revoked_by=? WHERE id=?",(u[0]['id'],grant['id']));c.commit()
    with pytest.raises(Denied):dashboard.report(c,u[1],{'active':'all'},presentation=True)
    assert dashboard.report(c,u[1],{},presentation=True)['total']==32
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],));c.commit()
    with pytest.raises(Denied):dashboard.report(c,u[2],{},presentation=True)


def test_presentation_limit_refuses_truncation_and_dashboard_still_pages(supplies_db,monkeypatch):
    c,u,_,_=supplies_db;setup_catalog(c,u)
    for index in range(3):
        item=create(c,u[1],code=f'LOW-{index}')
        opening(c,u[1],item,quantity='1')
    monkeypatch.setattr(dashboard,'MAX_PRESENTATION_ITEMS',2)
    with pytest.raises(Invalid,match='Narrow the dashboard filters'):
        dashboard.report(c,u[2],{},presentation=True)
    assert len(dashboard.report(c,u[2],{})['low_items'])==3
    assert len(dashboard.report(c,u[2],{'q':'LOW-0'},presentation=True)['low_items'])==1
