"""Private native preferences: owner boundaries, validated state and atomic revisions."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
import pytest
import auth
import storage as st
import travel_grid as grid
from tests.test_travel_grid import claims


def state(**over):
    return {'schema':1,**{k:v for k,v in grid.parse({}).items() if k in grid.VIEW_FIELDS},**over}


def post(client,**fields):
    return client.post('/travel/table/views',content=urlencode(fields),
        headers={'Content-Type':'application/x-www-form-urlencoded'},follow_redirects=False)


def create(client,name='Pending',**over):
    return post(client,action='create',name=name,state=json.dumps(state(**over)))


def test_create_open_replace_delete_and_export_keep_own_scope(claims,viewer,admin):
    c,owner,other,add=claims
    for i in range(1,36):add(i, status='ready' if i>30 else 'open')
    add(99,user_id=other,act_title='PRIVATE_OTHER')
    before=c.execute('SELECT * FROM travel_filing').fetchall()
    r=create(viewer,status='ready',sort='ref_code',dir='asc')
    assert r.status_code==303 and r.headers['cache-control']=='no-store' and 'status=ready' in r.headers['location']
    view=grid.views(c,owner)[0]
    assert grid.open_view(c,owner,view['id'])==state(status='ready',sort='ref_code',dir='asc')
    page=viewer.get(f'/travel/table?view={view["id"]}&page=2&status=open&user_id={other}')
    assert 'page 1 of 1' in page.text and 'TF-2610-0031' in page.text and 'TF-2610-0001' not in page.text
    assert 'PRIVATE_OTHER' not in page.text
    csv=viewer.get(f'/travel/table?view={view["id"]}&format=csv')
    assert csv.headers['x-export-rows']=='5'
    for params in ['', '&format=json','&format=csv']:
        r=admin.get(f'/travel/table?view={view["id"]}'+params)
        assert r.status_code==400 and 'TF-2610-0031' not in r.text
    r=post(viewer,action='update',id=view['id'],revision=view['revision'],name='Renamed',state=json.dumps(state(q='Visit 035')))
    assert r.status_code==303 and grid.views(c,owner)[0]['revision']==2
    assert grid.open_view(c,owner,view['id'])['q']=='Visit 035'
    assert post(viewer,action='delete',id=view['id'],revision=2).status_code==303
    assert grid.views(c,owner)==[] and viewer.get(f'/travel/table?view={view["id"]}').status_code==400
    assert c.execute('SELECT * FROM travel_filing').fetchall()==before


def test_names_cap_unicode_duplicates_and_other_owner_are_independent(claims,viewer,admin):
    c,owner,other,add=claims
    assert create(viewer,name='Straße').status_code==303
    assert create(viewer,name='STRASSE').status_code==400
    assert create(admin,name='STRASSE').status_code==303
    for i in range(9):assert create(viewer,name=f'View {i}').status_code==303
    assert create(viewer,name='Eleventh').status_code==400 and len(grid.views(c,owner))==10
    v=grid.views(c,owner)[0]
    assert post(viewer,action='update',id=v['id'],revision=v['revision'],name=v['name'],state=json.dumps(state(status='ready'))).status_code==303


@pytest.mark.parametrize('bad',[{'schema':2},{'schema':True},{'sort':'id;DROP TABLE travel_filing'},
 {'status':'approved'},{'q':'x'*201},{'from':'2026-02-30'},{'user_id':999},{'page':2},{'columns':['answers_json']}])
def test_reject_invalid_or_extra_saved_state(claims,viewer,bad):
    r=post(viewer,action='create',name='Bad',state=json.dumps(state(**bad)))
    assert r.status_code==400 and grid.views(claims[0],claims[1])==[]


def test_owner_forgery_stale_updates_deletes_and_invalid_names(claims,viewer,admin):
    c,owner,other,add=claims;assert create(viewer).status_code==303
    v=grid.views(c,owner)[0]
    for action in ['update','delete']:
        assert post(admin,action=action,id=v['id'],revision=1,name='Stolen',state=json.dumps(state())).status_code==400
    assert post(viewer,action='update',id=v['id'],revision=1,name='Current',state=json.dumps(state())).status_code==303
    for action in ['update','delete']:
        r=post(viewer,action=action,id=v['id'],revision=1,name='Stale',state=json.dumps(state()))
        assert r.status_code==409 and 'changed in another tab' in r.text and r.headers['cache-control']=='no-store'
    for name in ['', 'x'*61, 'two\nlines']:
        assert create(viewer,name=name).status_code==400
    assert grid.views(c,owner)[0]['name']=='Current'


def test_origin_body_limits_disabled_revoked_and_no_login(claims,viewer,client):
    c,owner,other,add=claims
    data={'action':'create','name':'Private','state':json.dumps(state())}
    r=viewer.post('/travel/table/views',content=urlencode(data),headers={'Origin':'https://evil.example','Content-Type':'application/x-www-form-urlencoded'})
    assert r.status_code==403 and grid.views(c,owner)==[]
    assert viewer.post('/travel/table/views',content='x'*8193,headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code==413
    assert viewer.post('/travel/table/views',json=data).status_code==400
    st.set_setting(c,'travel.enabled','0');assert create(viewer).status_code==403
    st.set_setting(c,'travel.enabled','1')
    token=auth.parse_token(viewer.cookies.get(auth.COOKIE_NAME))
    c.execute('DELETE FROM login_session WHERE user_id=?',(owner,));c.commit()
    with pytest.raises(PermissionError):grid.save_view(c,token,data)
    for client_ in [viewer,client]:assert create(client_).status_code in (302,303,401,403)
    assert grid.views(c,owner)==[]


def test_atomic_revision_and_create_cap_under_concurrent_writers(claims,viewer,app_mod,monkeypatch):
    c,owner,other,add=claims;assert create(viewer).status_code==303
    v=grid.views(c,owner)[0];token=auth.parse_token(viewer.cookies.get(auth.COOKIE_NAME))
    def write(fields):
        conn=st.connect(app_mod.DB)
        try:
            grid.save_view(conn,token,fields);return 'ok'
        except ValueError as e:return type(e).__name__
        finally:conn.close()
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(write,[{'action':'update','id':str(v['id']),'revision':'1','name':n,'state':json.dumps(state())} for n in ['A','B']]))
    assert sorted(results)==['ViewConflict','ok'] and grid.views(c,owner)[0]['revision']==2
    monkeypatch.setattr(grid,'MAX_VIEWS',2)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(write,[{'action':'create','name':n,'state':json.dumps(state())} for n in ['C','D']]))
    assert sorted(results)==['ValueError','ok'] and len(grid.views(c,owner))==2


def test_schema_idempotency_corrupt_view_recovery_and_atomic_rollback(claims,viewer):
    c,owner,other,add=claims;assert create(viewer).status_code==303
    v=grid.views(c,owner)[0];st.init_db(c)
    assert len(grid.views(c,owner))==1
    c.execute('UPDATE travel_claim_view SET state_json=? WHERE id=?',('invalid',v['id']));c.commit()
    assert viewer.get('/travel/table').status_code==200
    assert viewer.get(f'/travel/table?view={v["id"]}').status_code==400
    c.execute("CREATE TRIGGER fail_view_update BEFORE UPDATE ON travel_claim_view BEGIN SELECT RAISE(ABORT,'forced'); END");c.commit()
    token=auth.parse_token(viewer.cookies.get(auth.COOKIE_NAME))
    with pytest.raises(sqlite3.IntegrityError):grid.save_view(c,token,{'action':'update','id':v['id'],'revision':1,'name':'Changed','state':json.dumps(state())})
    assert grid.views(c,owner)[0]['name']=='Pending' and grid.views(c,owner)[0]['revision']==1
    c.execute('DROP TRIGGER fail_view_update');c.commit()
    assert post(viewer,action='delete',id=v['id'],revision=1).status_code==303
