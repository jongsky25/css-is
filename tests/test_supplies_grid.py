"""Interactive inventory shares classifier, live scope, exact sorting and private preferences."""
import csv
import io
from copy import deepcopy

import pytest
import storage as st
import supplies as s
import supplies_grid as grid
from supplies_notify import classify
from supplies_storage import Denied, Invalid, Conflict
from tests.test_supplies import supplies_db, setup_catalog, create, key
from tests.test_supplies_stock import opening


def state(**changes):
    return {'schema':1, 'q':'', 'unit':'', 'physical':'', 'availability':'', 'active':'active',
            'sort':'code', 'dir':'asc', 'columns':{field:{'visible':True} for field in grid.COLUMNS}, **changes}


def save(c, user, name='Inventory', **changes):
    result=grid.save_view(c,user,{'action':'create','name':name,'state':state(**changes)})
    return next(v for v in result['views'] if v['id']==result['saved_id'])


def test_global_filter_sort_pagination_export_and_fresh_inactive_scope(supplies_db):
    c,u,_,_=supplies_db
    grant=setup_catalog(c,u)
    ids=[]
    for index in range(65):
        item=create(c,u[1],code=f'INV-{index:03}',unit='Ream' if index<61 else 'Box')
        opening(c,u[1],item,quantity='2' if index<31 else '9')
        ids.append(item['id'])
    hidden=create(c,u[1],code='HIDDEN',unit='Secret unit')
    c.execute('UPDATE supply_item SET active=0 WHERE id=?',(hidden['id'],));c.commit()
    params={'q':'INV-','unit':'Ream','physical':'critical','availability':'low_available',
            'sort':'code','dir':'desc'}
    first=grid.page(c,u[2],params);second=grid.page(c,u[2],{**params,'page':'2'})
    assert first['last_row']==31 and first['last_page']==2
    assert [r['id'] for r in first['data']+second['data']]==[str(i) for i in reversed(ids[:31])]
    content,count=grid.export_csv(c,u[2],{**params,'columns':'description,code,available'})
    exported=list(csv.reader(io.StringIO(content.removeprefix('\ufeff'))))
    assert count==31 and exported[0]==['Description','Code','Available']
    assert [r[1] for r in exported[1:]]==[f'INV-{i:03}' for i in reversed(range(31))]
    assert all(r[2]=='2' for r in exported[1:])
    assert 'Secret unit' not in grid.units(c,u[2]) and 'Secret unit' in grid.units(c,u[1])
    with pytest.raises(Denied):grid.page(c,u[0],{'active':'all'}) # technical admin is not stock reader
    assert grid.page(c,u[1],{'active':'inactive'})['last_row']==1
    saved=save(c,u[1],active='all')
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-24',revoked_by=? WHERE id=?",(u[0]['id'],grant['id']));c.commit()
    for action in (lambda:grid.page(c,u[1],saved['state']),lambda:grid.export_csv(c,u[1],{**saved['state'],'columns':'code'}),
                   lambda:save(c,u[1],name='No longer allowed',active='all')):
        with pytest.raises(Denied):action()
    assert grid.views(c,u[1])[0]['state']['active']=='all'
    assert grid.page(c,u[1],{})['last_row']==65
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],));c.commit()
    for action in (lambda:grid.page(c,u[2],{}),lambda:grid.export_csv(c,u[2],{}),lambda:grid.views(c,u[2])):
        with pytest.raises(Denied):action()


def test_stock_classifier_boundaries_unknowns_numeric_order_and_exact_csv(supplies_db):
    c,u,_,_=supplies_db;setup_catalog(c,u)
    items=[]
    for index,quantity in enumerate((None,'0','4','5','12')):
        item=create(c,u[1],code=f'S-{index}')
        if quantity is not None:opening(c,u[1],item,quantity=quantity)
        items.append(item)
    page=grid.page(c,u[2],{'sort':'on_hand','dir':'asc'})
    assert [r['on_hand'] for r in page['data']]==['0','4','5','12',None]
    assert [r['on_hand'] for r in grid.page(c,u[2],{'sort':'on_hand','dir':'desc'})['data']]==['12','5','4','0',None]
    for item in page['data']:
        expected=classify(int(item['on_hand'] or 0),0,5,recorded=item['on_hand'] is not None)
        assert item['physical']==expected['physical_state'] and item['availability']==expected['availability_state']
    assert grid.page(c,u[2],{'physical':'critical'})['last_row']==1
    assert grid.page(c,u[2],{'physical':'out_of_stock'})['last_row']==1
    assert grid.page(c,u[2],{'physical':'unrecorded'})['last_row']==1
    # Ledger quantities legitimately exceed a single posting and JavaScript safe integers.
    # Simulate a valid 64-bit ledger aggregate without millions of bounded postings.
    class LargeSum:
        def __init__(self):self.total=0
        def step(self,value):self.total+=value or 0
        def finalize(self):return 9007199254740993 if self.total==12 else self.total
    c.create_aggregate('sum',1,LargeSum)
    assert grid.page(c,u[2],{'sort':'on_hand','dir':'desc'})['data'][0]['on_hand']=='9007199254740993'
    c.execute("UPDATE supply_item SET description='=HYPERLINK(\"x\")' WHERE id=?",(items[-1]['id'],));c.commit()
    content,count=grid.export_csv(c,u[2],{'columns':'code,description,on_hand,target_level','sort':'on_hand','dir':'desc'})
    data=list(csv.reader(io.StringIO(content.removeprefix('\ufeff'))))
    assert count==5 and data[1][1].startswith("'=HYPERLINK") and data[1][2]=='9007199254740993'
    assert data[-1][2]=='Not recorded'
    assert grid.page(c,u[2],{'q':'%_\' OR 1=1 --'})['last_row']==0
    assert grid.page(c,u[2],{'q':'not found','page':'10'})['page']==1


@pytest.mark.parametrize('params',[{'physical':'low'},{'availability':'critical'},{'active':'0'},
    {'unit':None},{'q':True},{'q':'x'*201},{'unit':'x'*41},{'sort':'quantity;DROP TABLE supply_item'},
    {'sort':[]},{'dir':'sideways'},{'physical':{}},{'page':'-1'},{'page':'2.5'},{'page':'9'*5000}])
def test_invalid_options_are_rejected(supplies_db,params):
    c,u,_,_=supplies_db
    with pytest.raises(Invalid):grid.page(c,u[2],params)
    if 'page' not in params:
        with pytest.raises(Invalid):grid.export_csv(c,u[2],params)
        with pytest.raises(Invalid):grid.view_state(state(**params))


def test_private_view_persistence_conflicts_quota_schema_and_read_only_data(supplies_db):
    c,u,_,path=supplies_db;setup_catalog(c,u);create(c,u[1])
    before={table:c.execute(f'SELECT * FROM {table}').fetchall() for table in
            ('supply_item','supply_stock_movement','supply_reservation','supply_operation','supply_event')}
    saved=save(c,u[2],physical='unrecorded')
    assert grid.views(c,u[1])==[]
    other=st.connect(path)
    assert grid.views(other,u[2])==[saved];other.close()
    changed=deepcopy(saved['state']);changed['columns']['available']['visible']=False
    updated=grid.save_view(c,u[2],{'action':'update','id':saved['id'],'revision':1,'name':'Changed','state':changed})
    assert updated['views'][0]['revision']==2
    for action in ('update','delete'):
        with pytest.raises(Conflict):grid.save_view(c,u[2],{'action':action,'id':saved['id'],'revision':1,'name':'Stale','state':state()})
        with pytest.raises(Invalid):grid.save_view(c,u[1],{'action':action,'id':saved['id'],'revision':2,'name':'Stolen','state':state()})
    with pytest.raises(Invalid):save(c,u[2],name='changed')
    for index in range(9):save(c,u[2],name=f'View {index}')
    with pytest.raises(Invalid,match='up to 10'):save(c,u[2],name='Excess')
    for bad in (state(schema=True),state(extra=True),state(columns={}),state(columns={**state()['columns'],'code':{'visible':False}})):
        with pytest.raises(Invalid):grid.view_state(bad)
    grid.page(c,u[2],{});grid.export_csv(c,u[2],{})
    st.init_db(c);st.init_db(c)
    assert len(grid.views(c,u[2]))==10
    assert before=={table:c.execute(f'SELECT * FROM {table}').fetchall() for table in before}
    grid.save_view(c,u[2],{'action':'delete','id':saved['id'],'revision':2})
    newer=save(c,u[2],name='New identity')
    assert newer['id']>saved['id']


def test_export_limit_and_column_allowlist(supplies_db,monkeypatch):
    c,u,_,_=supplies_db;setup_catalog(c,u)
    for index in range(3):create(c,u[1],code=f'LIMIT-{index}')
    monkeypatch.setattr(grid,'MAX_EXPORT_ROWS',2)
    with pytest.raises(Invalid,match='10,000'):grid.export_csv(c,u[2],{})
    assert grid.export_csv(c,u[2],{'q':'LIMIT-1'})[1]==1
    for columns in ('','description','code,code','code,revision','code;DROP TABLE supply_item'):
        with pytest.raises(Invalid):grid.export_csv(c,u[2],{'columns':columns})


from tests.test_supplies_requests import request_db
from tests.test_supplies_approvals import approval_db
from tests.test_supplies_backorders import ready
from tests.test_supplies_stock import receive


def test_reservations_drive_availability_without_changing_physical_stock(approval_db):
    c,u,_,_,item=approval_db
    ready(c,u,item,'10')
    fully=grid.page(c,u[2],{'availability':'fully_reserved'})
    assert fully['last_row']==1 and fully['data'][0]['physical']=='normal'
    assert fully['data'][0]['reserved']=='10' and fully['data'][0]['available']=='0'
    receive(c,u[1],s.get_item(c,u[1],item),quantity='5')
    assert grid.page(c,u[2],{'availability':'available'})['data'][0]['available']=='5'
    ready(c,u,item,'3')
    low=grid.page(c,u[2],{'availability':'low_available','physical':'normal'})
    assert low['last_row']==1 and low['data'][0]['available']=='2'
    assert grid.page(c,u[2],{'physical':'critical'})['last_row']==0


def test_inventory_http_json_csrf_errors_cache_and_disabled_reads(app_mod,viewer):
    import re
    c=st.connect(app_mod.DB)
    user=st.get_admin_user(c,'viewer@test.local')
    c.execute('''INSERT INTO supply_item(code,description,unit,created_by,created_at,updated_at)
        VALUES ('HTTP-1','Synthetic read-only item','Piece',?,'2026-10-19','2026-10-19')''',(user['id'],));c.commit()
    assert not s.enabled(c)
    html=viewer.get('/supplies/items')
    assert html.status_code==200 and 'supplies-grid.js?v=' in html.text
    token=re.search(r'data-csrf="([a-f0-9]+)"',html.text)[1]
    for path in ('/supplies/inventory-data','/supplies/inventory-export.csv','/supplies/inventory-views'):
        result=viewer.get(path)
        assert result.status_code==200 and result.headers['cache-control']=='no-store'
    for path in ('/supplies/inventory-data','/supplies/inventory-export.csv'):
        bad=viewer.get(path,params={'sort':'DROP TABLE supply_item'})
        assert bad.status_code==400 and bad.headers['cache-control']=='no-store'
        forbidden=viewer.get(path,params={'active':'all'})
        assert forbidden.status_code==403 and forbidden.headers['cache-control']=='no-store'
    payload={'action':'create','name':'HTTP view','state':state()}
    assert viewer.post('/supplies/inventory-views',json=payload).status_code==403
    headers={'X-CSRF-Token':token}
    saved=viewer.post('/supplies/inventory-views',headers=headers,json=payload)
    assert saved.status_code==200 and saved.headers['cache-control']=='no-store'
    view=saved.json()['views'][0]
    assert viewer.post('/supplies/inventory-views',headers=headers,json=payload).status_code==400
    changed={**payload,'action':'update','id':view['id'],'revision':0}
    assert viewer.post('/supplies/inventory-views',headers=headers,json=changed).status_code==400
    changed['revision']=1
    assert viewer.post('/supplies/inventory-views',headers=headers,json=changed).status_code==200
    assert viewer.post('/supplies/inventory-views',headers=headers,json=changed).status_code==409
    assert viewer.post('/supplies/inventory-views',headers=headers,content=b'[').status_code==400
    assert viewer.post('/supplies/inventory-views',headers=headers,content=b' '*32769).status_code==400
    exported=viewer.get('/supplies/inventory-export.csv',params={'columns':'code,on_hand'})
    assert exported.headers['x-export-rows']=='1' and 'supply-inventory.csv' in exported.headers['content-disposition']
    assert 'Not recorded' in exported.text
    c.close()


def test_preferences_never_project_pending_stock_notices(supplies_db,monkeypatch):
    c,u,_,_=supplies_db;setup_catalog(c,u)
    item=create(c,u[1]);opening(c,u[1],item,quantity='0')
    c.execute('UPDATE supply_alert_event SET processed_at=NULL');c.commit()
    pending=c.execute('SELECT COUNT(*) FROM supply_alert_event WHERE processed_at IS NULL').fetchone()[0]
    assert pending>0
    def unexpected(*args,**kwargs):raise AssertionError('Preferences must not project stock notices')
    monkeypatch.setattr('supplies_notify.process_pending',unexpected)
    save(c,u[2])
    assert c.execute('SELECT COUNT(*) FROM supply_alert_event WHERE processed_at IS NULL').fetchone()[0]==pending
