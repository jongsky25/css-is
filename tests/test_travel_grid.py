"""Owner isolation, real server pagination/filtering and read-only recorded semantics."""
from urllib.parse import urlencode
import pytest
import storage as st
import travel_grid as grid


@pytest.fixture
def claims(app_mod):
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'travel.enabled', '1')
    owner = st.get_admin_user(conn, 'viewer@test.local')['id']
    other = st.get_admin_user(conn, 'admin@test.local')['id']
    def add(index, **over):
        fields = dict(user_id=owner, ref_code=f'TF-2610-{index:04}', kind='liquidation', source_kind='blank',
                      act_title=f'Visit {index:03}', act_start='2026-10-01', act_end='2026-10-20', status='open',
                      answers_json='{"secret":"PRIVATE_ANSWER"}', dpo_no='PRIVATE_DPO')
        fields.update(over)
        conn.execute('INSERT INTO travel_filing ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')', tuple(fields.values()))
        conn.commit()
    yield conn, owner, other, add
    conn.close()


def test_own_only_json_and_html_even_for_administrator(claims, viewer, admin):
    c, owner, other, add = claims
    add(1, act_title='Owner visible'); add(2, user_id=other, act_title='Other private')
    for client, yes, no in [(viewer, 'Owner visible', 'Other private'), (admin, 'Other private', 'Owner visible')]:
        for suffix in ['', '?format=json&user_id='+str(owner)]:
            response = client.get('/travel/table'+suffix)
            assert response.status_code==200 and response.headers['cache-control']=='no-store'
            assert yes in response.text and no not in response.text
            assert 'PRIVATE_ANSWER' not in response.text and 'PRIVATE_DPO' not in response.text
    assert set(viewer.get('/travel/table?format=json').json()['data'][0])==set(grid.COLUMNS)|{'href'}


def test_pagination_order_filters_and_clamp_cover_all_records(claims, viewer):
    c, owner, other, add = claims
    for i in range(1,66): add(i, status='submitted' if i==65 else 'open')
    first = viewer.get('/travel/table?format=json&sort=ref_code&dir=asc').json()
    second = viewer.get('/travel/table?format=json&sort=ref_code&dir=asc&page=2').json()
    assert first['total']==65 and len(first['data'])==len(second['data'])==30
    assert first['data'][-1]['ref_code']=='TF-2610-0030' and second['data'][0]['ref_code']=='TF-2610-0031'
    last = viewer.get('/travel/table?format=json&sort=ref_code&dir=asc&page=999').json()
    assert last['page']==last['last_page']==3 and len(last['data'])==5
    assert viewer.get('/travel/table?format=json&status=submitted&kind=liquidation').json()['total']==1
    assert viewer.get('/travel/table?format=json&from=2026-10-21').json()['total']==0
    assert viewer.get('/travel/table?format=json&from=2026-10-20&to=2026-10-20').json()['total']==65
    html = viewer.get('/travel/table?sort=ref_code&dir=asc&page=2&status=open').text
    assert 'TF-2610-0031' in html and 'Previous page' in html and 'Next page' in html
    assert 'status=open' in html and 'sort=ref_code' in html


def test_literal_unicode_search_and_markup_are_safe(claims, viewer):
    c, owner, other, add = claims
    add(1, act_title='Straße 100%_ <img src=x onerror=alert(1)>')
    add(2, act_title='plain')
    for q in ['STRASSE', '100%_', '<img', 'TF-2610-0001']:
        assert viewer.get('/travel/table?'+urlencode({'format':'json', 'q':q})).json()['total']==1
    assert '&lt;img' in viewer.get('/travel/table').text
    assert viewer.get('/travel/table?format=json&q=%25').json()['total']==1


@pytest.mark.parametrize('query',[{'sort':'id desc; DROP TABLE travel_filing'}, {'dir':'random'}, {'status':'approved'},
    {'kind':'all'}, {'from':'2026-02-30'}, {'from':'20261001'}, {'from':'2026-10-20','to':'2026-10-01'},
    {'page':'0'}, {'page':'no'}, {'page':'100001'}, {'q':'x'*201}])
def test_invalid_selection_is_explained_without_data(claims, viewer, query):
    claims[3](1, act_title='PRIVATE_MATCH')
    for json in [False, True]:
        r=viewer.get('/travel/table?'+urlencode({**query, **({'format':'json'} if json else {})}))
        assert r.status_code==400 and r.headers['cache-control']=='no-store' and 'PRIVATE_MATCH' not in r.text
        assert ('error' in r.json()) if json else ('Reset claims table' in r.text)


def test_no_writes_and_no_deadline_refresh(claims, viewer):
    c, owner, other, add = claims
    eid=st.cal_create(c,'Moved activity','2026-12-01',end_date='2026-12-05')
    add(1, entry_id=eid, act_start='2026-10-01',act_end='2026-10-20',deadline_date='2026-11-19')
    before=c.execute('SELECT * FROM travel_filing').fetchall()
    for suffix in ['', '?format=json']:
        assert viewer.get('/travel/table'+suffix).status_code==200
    assert c.execute('SELECT * FROM travel_filing').fetchall()==before
    changes=c.total_changes
    grid.snapshot(c, owner, grid.parse({}))
    assert c.total_changes==changes


def test_switch_off_and_revocation_stop_private_data(claims, viewer):
    c, owner, other, add = claims; add(1, act_title='PRIVATE_MATCH')
    st.set_setting(c,'travel.enabled','0')
    for suffix in ['', '?format=json']:
        r=viewer.get('/travel/table'+suffix)
        assert 'PRIVATE_MATCH' not in r.text and r.headers['cache-control']=='no-store'
    st.set_setting(c,'travel.enabled','1')
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(owner,));c.commit()
    r=viewer.get('/travel/table?format=json',follow_redirects=False)
    assert r.status_code in (302,303,401,403) and 'PRIVATE_MATCH' not in r.text


def test_no_login_cannot_read_table(client):
    r=client.get('/travel/table?format=json',follow_redirects=False)
    assert r.status_code in (302,303,401,403)
