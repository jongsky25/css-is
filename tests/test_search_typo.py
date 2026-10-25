"""Bounded typo matches are suggestions, not permission or identity substitutions."""
import pytest
import auth
from tests.conftest import session_token

import search_typo as typo
import search_sources as sources
import storage as st
from tests.test_colleague_status import org, _client, _report, SECRET


@pytest.mark.parametrize('query,target',[
    ('reimbursment','Travel reimbursements'),('jhon','John Mendoza'),
    ('calender','Office calendar'),('calenar','Office calendar'),
    ('jose','José Mendoza'),('jteq calendar','Jteq calender'),
])
def test_small_spelling_differences_are_close(query,target):
    assert typo.close_score(query,target) is not None


@pytest.mark.parametrize('query,target',[
    ('john','John Mendoza'),('bob','Bob'),('bbo','Bob'),
    ('1234','1235'),('calendar 202-6','calendar 2026'),
    ('calender 2026','calendar 2027'),('calender pineapple','Office calendar'),
    ('zxqv','Office calendar'),('calndxx','calendar'),
    ('x'*129,'calendar'),('word '*9,'word calendar'),
])
def test_exact_or_unsafe_or_unrelated_queries_do_not_become_close(query,target):
    assert typo.close_score(query,target) is None


def test_ranking_is_bounded_deduplicated_and_excludes_exact_destinations():
    def row(i):return {'title':'Calendar '+str(i),'url':'/cal/'+str(i),'section':'Go to'}
    candidates=[(row(i),'Calendar') for i in range(8)]
    candidates.insert(1,(row(0),'Calendar'))
    result=typo.rank('calender',candidates,excluded=['/cal/2'])
    assert len(result)==5 and len({r['url'] for r in result})==5
    assert '/cal/2' not in {r['url'] for r in result}
    assert all(r['match']=='close' for r in result)
    assert result==typo.rank('calender',candidates,excluded=['/cal/2'])
    assert not typo.rank('calender',candidates*(typo.MAX_CANDIDATES//len(candidates)+1))
    assert typo.close_score('calender','calendar '+'x'*typo.MAX_TEXT) is None


def test_navigation_and_guides_are_filtered_before_matching(app_mod,viewer,admin,monkeypatch):
    original=sources.search_typo.rank;observed=[]
    def capture(query,candidates,excluded=()):
        observed.extend(row['url'] for row,text in candidates)
        return original(query,candidates,excluded)
    monkeypatch.setattr(sources.search_typo,'rank',capture)
    rows=viewer.get('/api/search?q=auidt&suggest_pages=1').json()
    assert '/admin/audit' not in observed and not any(r['url'].startswith('/admin/audit') for r in rows)
    observed.clear()
    rows=admin.get('/api/search?q=auidt&suggest_pages=1').json()
    assert '/admin/audit' in observed
    assert any(r['url']=='/admin/audit' and r.get('match')=='close' for r in rows)
    # Current role/capabilities are reloaded, rather than trusting the old cookie.
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'admin@test.local')
    conn.execute("UPDATE admin_user SET role='viewer' WHERE id=?",(user['id'],));conn.commit();conn.close()
    observed.clear()
    assert admin.get('/api/search?q=auidt&suggest_pages=1',follow_redirects=False).status_code==303
    assert not observed
    admin.cookies.set(auth.COOKIE_NAME,session_token({**user,'role':'viewer'}))
    rows=admin.get('/api/search?q=auidt&suggest_pages=1').json()
    assert '/admin/audit' not in observed and not any(r['url'].startswith('/admin/audit') for r in rows)


def test_exact_records_precede_labeled_close_matches_and_scope_is_retained(admin,monkeypatch):
    monkeypatch.setattr(sources,'run_sources',lambda *args:[{'title':'Exact calender task','url':'/exact','section':'My to-do','hint':''}])
    response=admin.get('/api/search?q=calender&suggest_pages=1')
    rows=response.json()
    assert response.headers['cache-control']=='no-store'
    assert rows[0]['url']=='/exact' and rows[-1].get('match')=='close'
    scoped=admin.get('/api/search?q=reimbursment&suggest_pages=1&scope=css').json()
    assert not any(r.get('match')=='close' and r['section'] in ('Office','Help','Colleagues') for r in scoped)


def test_approximate_failure_keeps_existing_exact_results_and_does_not_log_terms(admin,monkeypatch,caplog):
    monkeypatch.setattr(sources,'run_sources',lambda *args:[{'title':'Exact result','url':'/exact','section':'Activities','hint':''}])
    def fail(*args,**kwargs):raise RuntimeError('synthetic failure')
    monkeypatch.setattr(sources.search_typo,'rank',fail)
    response=admin.get('/api/search?q=private-search-term&suggest_pages=1')
    assert response.status_code==200 and response.json()[0]['url']=='/exact'
    assert 'private-search-term' not in caplog.text


def test_colleague_suggestions_keep_status_scope_and_exclude_inactive_staff(app_mod,org):
    conn=org['conn'];today=app_mod._today_local()
    _report(conn,org['bob'],today,'field',SECRET)
    st.set_colleague_status_scope(conn,'team')
    client=_client(app_mod,conn,org['unlinked'])
    rows=client.get('/api/search?q=ztea bob').json()
    bob=next(r for r in rows if r['url']==f"/people/{org['bob']}")
    assert bob['match']=='close' and SECRET not in str(rows)
    assert 'In the field today' not in bob['hint']
    assert not any(r['section']=='Colleagues' for r in client.get('/api/search?q=ztea bob&scope=css').json())
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(org['bob'],));conn.commit()
    assert not any(r['url']==f"/people/{org['bob']}" for r in client.get('/api/search?q=ztea bob').json())


def test_personal_record_text_is_never_a_fuzzy_candidate(app_mod,viewer,monkeypatch):
    conn=st.connect(app_mod.DB)
    st.cal_create(conn,'Secret reimbursement planning','2026-10-24',audience='people',by='admin@test.local')
    conn.close()
    observed=[];original=sources.search_typo.rank
    def capture(query,candidates,excluded=()):
        observed.extend(text for row,text in candidates)
        return original(query,candidates,excluded)
    monkeypatch.setattr(sources.search_typo,'rank',capture)
    viewer.get('/api/search?q=reimbursment&suggest_pages=1')
    assert not any('Secret reimbursement planning' in text for text in observed)


def test_fallback_keeps_its_exact_page_results_and_offers_labeled_close_destinations(admin):
    exact=admin.get('/search?q=trends')
    assert '1 result' in exact.text and exact.headers['cache-control']=='no-store'
    response=admin.get('/search?q=reimbursment')
    assert response.status_code==200 and 'Close matches' in response.text
    assert '>My travel claims<' in response.text and 'Close match · Travel' in response.text


def test_oversized_directory_refuses_fuzzy_staff_without_truncating_other_sources(monkeypatch):
    monkeypatch.setattr(st,'colleague_directory',lambda conn:[{}]*2001)
    monkeypatch.setattr(st,'colleague_status_for',lambda *args:pytest.fail('No staff should be ranked'))
    ctx={'help_catalog':lambda:[],'today':None}
    page={'title':'Calendar','hint':'','kw':'','section':'Calendar','url':'/calendar','mod':'calendar'}
    assert sources.close_matches(None,None,'calender',ctx,pages=[page])[0]['url']=='/calendar'
    monkeypatch.setattr(st,'colleague_directory',lambda conn:pytest.fail('Short/numeric queries should skip candidates'))
    assert sources.close_matches(None,None,'1234',ctx,pages=[page])==[]


def test_archived_staff_are_not_close_candidates(app_mod,org):
    conn=org['conn'];client=_client(app_mod,conn,org['unlinked'])
    conn.execute('UPDATE resource_person SET archived_at=? WHERE id=(SELECT rp_id FROM admin_user WHERE id=?)',('2026-10-20',org['bob']));conn.commit()
    assert not any(r['url']==f"/people/{org['bob']}" for r in client.get('/api/search?q=ztea bob').json())
