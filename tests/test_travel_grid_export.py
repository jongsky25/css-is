"""Complete current-selection downloads, fresh owner scope and spreadsheet-safe text."""
import csv
import io
from urllib.parse import urlencode
import pytest
import storage as st
import travel_grid as grid
from tests.test_travel_grid import claims


def read(response):
    assert response.status_code==200
    assert response.headers['content-type'].startswith('text/csv')
    assert response.headers['cache-control']=='no-store'
    assert response.headers['content-disposition']=='attachment; filename="travel-claims.csv"'
    assert response.text.startswith('\ufeff')
    return list(csv.reader(io.StringIO(response.text.removeprefix('\ufeff'))))


def test_complete_selection_all_pages_and_matching_labels(claims,viewer):
    c,owner,other,add=claims
    for i in range(1,66):add(i,status='ready' if i<64 else 'open')
    add(100,user_id=other,act_title='PRIVATE_OTHER')
    add(101,kind='ca')
    params={'format':'csv','status':'ready','kind':'liquidation','from':'2026-10-20','to':'2026-10-20',
            'q':'visit','sort':'ref_code','dir':'desc','page':2}
    response=viewer.get('/travel/table?'+urlencode(params));rows=read(response)
    assert rows[0]==list(grid.COLUMNS.values()) and len(rows)==64
    assert [r[0] for r in rows[1:]]==[f'TF-2610-{i:04}' for i in range(63,0,-1)]
    assert all(r[1]=='Liquidation' and r[5]=='Ready to sign' for r in rows[1:])
    assert response.headers['x-export-rows']=='63'
    assert 'PRIVATE_OTHER' not in response.text and 'PRIVATE_DPO' not in response.text and 'PRIVATE_ANSWER' not in response.text
    params['format']='json';params['page']=1
    first=viewer.get('/travel/table?'+urlencode(params)).json()['data']
    assert rows[1:31]==[[r[k] for k in grid.COLUMNS] for r in first]


def test_export_rechecks_owner_changes_administrator_and_disabled_feature(claims,viewer,admin):
    c,owner,other,add=claims;add(1,act_title='Original owner');add(2,user_id=other,act_title='Other owner')
    assert read(viewer.get('/travel/table?format=csv'))[1][2]=='Original owner'
    assert read(admin.get('/travel/table?format=csv'))[1][2]=='Other owner'
    c.execute('UPDATE travel_filing SET user_id=? WHERE ref_code=?',(other,'TF-2610-0001'));c.commit()
    assert len(read(viewer.get('/travel/table?format=csv&user_id='+str(other))))==1
    st.set_setting(c,'travel.enabled','0')
    r=viewer.get('/travel/table?format=csv')
    assert 'attachment' not in r.headers.get('content-disposition','') and 'Other owner' not in r.text
    assert r.headers['cache-control']=='no-store'


def test_unicode_literal_search_formula_quoting_and_linebreaks(claims,viewer):
    c,owner,other,add=claims
    titles=['=HYPERLINK("x")',' +SUM(1,2)','-1+1','@SUM(1,2)','\t=cmd','\r=cmd','\n=cmd',
            'Straße ñ 100%_, "quote"\nsecond line']
    for i,title in enumerate(titles,1):add(i,act_title=title)
    rows=read(viewer.get('/travel/table?format=csv&sort=ref_code&dir=asc'))
    assert [r[2] for r in rows[1:]]==["'"+t for t in titles[:-1]]+titles[-1:]
    for q in ['STRASSE','100%_']:
        result=read(viewer.get('/travel/table?'+urlencode({'format':'csv','q':q})))
        assert len(result)==2 and result[1][2]==titles[-1]


def test_empty_selection_and_read_only_recorded_dates(claims,viewer):
    c,owner,other,add=claims
    eid=st.cal_create(c,'Moved activity','2026-12-01',end_date='2026-12-05')
    add(1,entry_id=eid,deadline_date='2026-11-19')
    before=c.execute('SELECT * FROM travel_filing').fetchall();changes=c.total_changes
    rows=read(viewer.get('/travel/table?format=csv'))
    assert rows[1][3:5]==['2026-10-01','2026-10-20']
    assert c.execute('SELECT * FROM travel_filing').fetchall()==before
    grid.export_csv(c,owner,grid.parse({}));assert c.total_changes==changes
    assert len(read(viewer.get('/travel/table?format=csv&q=absent')))==1


def test_limit_refuses_partial_attachment_counts_only_matches_and_owner(claims,viewer,monkeypatch):
    c,owner,other,add=claims
    monkeypatch.setattr(grid,'MAX_EXPORT_ROWS',2)
    for i in range(1,4):add(i, status='ready' if i<3 else 'open')
    for i in range(4,8):add(i,user_id=other)
    r=viewer.get('/travel/table?format=csv&sort=ref_code&dir=asc')
    assert r.status_code==400 and r.headers['cache-control']=='no-store'
    assert 'attachment' not in r.headers.get('content-disposition','') and '10,000' in r.text
    assert 'Return to claims table' in r.text and 'TF-2610-0001' not in r.text
    assert len(read(viewer.get('/travel/table?format=csv&status=ready')))==3


@pytest.mark.parametrize('params',[{'sort':'id;DROP TABLE travel_filing'}, {'status':'approved'},
    {'from':'2026-02-30'}, {'from':'2026-10-20','to':'2026-10-01'}, {'q':'x'*201}])
def test_invalid_export_has_no_records_or_attachment(claims,viewer,params):
    claims[3](1,act_title='PRIVATE_CLAIM')
    r=viewer.get('/travel/table?'+urlencode({'format':'csv',**params}))
    assert r.status_code==400 and r.headers['cache-control']=='no-store'
    assert 'attachment' not in r.headers.get('content-disposition','') and 'PRIVATE_CLAIM' not in r.text


def test_revoked_session_and_no_login_do_not_download(claims,viewer,client):
    c,owner,other,add=claims;add(1,act_title='PRIVATE_CLAIM')
    c.execute('DELETE FROM login_session WHERE user_id=?',(owner,));c.commit()
    for browser in [viewer,client]:
        r=browser.get('/travel/table?format=csv',follow_redirects=False)
        assert r.status_code in (302,303,401,403) and 'PRIVATE_CLAIM' not in r.text
        assert 'attachment' not in r.headers.get('content-disposition','')
