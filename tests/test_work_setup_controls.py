"""Instance controls and setup diagnostics; no live transport or automatic enablement."""
import json

import pytest
from starlette.testclient import TestClient

import auth
import apprise_transport as transport
import documents as docs
import documents_permissions as permissions
import storage as st
import work
import work_channels as channels
from tests.conftest import session_token
from tests.test_documents_setup import setup_db, hidden


def appoint(conn, user):
    docs.bootstrap_admins(conn,user,docs.preview_admin_setup(conn,user,user['username'],'Owner appointed administrator'))


def test_explicit_work_control_requires_documents_and_audits_shared_revision(setup_db):
    conn,users,_=setup_db;user=users[0];appoint(conn,user)
    before=conn.total_changes
    with pytest.raises(ValueError,match='Enable Documents'):
        work.set_module_enabled(conn,user,True,'0','Enable discussion pilot')
    assert conn.total_changes==before
    docs.set_module_enabled(conn,user,True,'0','Enable Documents first')
    with pytest.raises(docs.Conflict):work.set_module_enabled(conn,user,True,'0','Stale page')
    work.set_module_enabled(conn,user,True,'1','Enable discussion pilot')
    assert work.enabled(conn) and st.get_setting(conn,'documents.sending_enabled')=='0'
    assert st.get_setting(conn,'documents.settings_revision')=='2'
    row=conn.execute("SELECT actor_id,detail_json FROM document_event WHERE action='work_module_enabled'").fetchone()
    assert row[0]==user['id']
    assert json.loads(row[1])=={'before':{'work.enabled':'0'},'after':{'work.enabled':'1'},'authorization':'Enable discussion pilot'}
    assert conn.execute("SELECT count(*) FROM audit_log WHERE action='document_work_module_enabled'").fetchone()[0]==1
    with pytest.raises(docs.Conflict):docs.set_module_enabled(conn,user,False,'1','Stale Documents form')
    conn.execute("UPDATE document_role_grant SET revoked_at='2026-10-24'");conn.commit()
    # Emergency off remains available to a current system administrator.
    work.set_module_enabled(conn,user,False,'2','Stop pilot')
    assert not work.enabled(conn) and docs.enabled(conn)
    assert st.get_setting(conn,'documents.sending_enabled')=='0'
    with pytest.raises(permissions.Denied):work.set_module_enabled(conn,user,True,'3','Revoked authority')


def test_work_control_rechecks_system_role_scope_and_account(setup_db):
    conn,users,_=setup_db;admin=users[0]
    st.set_setting(conn,'documents.enabled','1')
    unit=st.add_org_unit(conn,'Scoped office','division','TEST/SCOPED')
    for uid,unit_id in [(admin['id'],unit),(users[1]['id'],None)]:
        conn.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'grant_admin',?,'2026-10-24')",(uid,unit_id))
    conn.commit()
    for user in [admin,{**users[1],'role':'admin'}]:
        with pytest.raises(permissions.Denied):work.set_module_enabled(conn,user,True,'0','Not all-unit system authority')
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(admin['id'],));conn.commit()
    with pytest.raises(permissions.Denied):work.set_module_enabled(conn,admin,False,'0','Inactive account')
    assert st.get_setting(conn,'work.enabled')=='0'


def test_work_control_rolls_back_on_audit_failure_and_requires_reason(setup_db,monkeypatch):
    conn,users,_=setup_db;appoint(conn,users[0]);st.set_setting(conn,'documents.enabled','1')
    with pytest.raises(ValueError):work.set_module_enabled(conn,users[0],True,'0','')
    def fail(*args,**kwargs):raise RuntimeError('audit unavailable')
    monkeypatch.setattr(docs,'event',fail)
    with pytest.raises(RuntimeError):work.set_module_enabled(conn,users[0],True,'0','Controlled setup')
    assert st.get_setting(conn,'work.enabled')=='0' and st.get_setting(conn,'documents.settings_revision','0')=='0'


def test_work_control_http_csrf_confirmation_conflict_and_owner_authority(setup_db,app_mod,monkeypatch):
    conn,users,path=setup_db;appoint(conn,users[0]);st.set_setting(conn,'documents.enabled','1')
    monkeypatch.setattr(app_mod,'DB',path)
    monkeypatch.delenv('CSS_BASE_URL',raising=False)
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(users[0]))
        url='/admin/documents/setup';page=client.get(url)
        assert 'Enable Collaborative work</button>' in page.text
        form={'action':'enable_work','settings_revision':'0','authorization':'Enable pilot'}
        assert client.post(url,data=form).status_code==403
        form['csrf']=hidden(page,'csrf')
        assert client.post(url,data=form).status_code==400
        form['confirmed']='yes'
        result=client.post(url,data=form,follow_redirects=False)
        assert result.status_code==303 and result.headers['location'].endswith('#collaborative-work')
        assert work.enabled(conn)
        assert client.post(url,data=form).status_code==409
        client.cookies.set(auth.COOKIE_NAME,session_token(users[1]))
        assert client.get(url).status_code==403
        assert client.post(url,data={**form,'settings_revision':'1','action':'disable_work'}).status_code==403
        assert work.enabled(conn)


@pytest.mark.parametrize('raw,fragment',[
    ('','is missing'),('{broken','not valid JSON'),('[]','must be a JSON object'),
    ('{}','current setup code has no entry'),
    (json.dumps({'a'*32:{'bot_token':'hidden-token','chat_id':'123'}}),'bot_token has an invalid format'),
    (json.dumps({'a'*32:{'bot_token':'123456:'+('A'*35),'chat_id':123}}),'chat_id must be a positive private'),
    (json.dumps({'a'*32:{'bot_token':'123456:'+('A'*35),'chat_id':'123','extra':'hidden-secret'}}),'exactly bot_token and chat_id'),
    ('x'*65537,'exceeds the size limit'),
])
def test_target_diagnostics_do_not_echo_configuration(raw,fragment,monkeypatch):
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',raw)
    value,issue=transport.target_check('a'*32)
    assert value is None and fragment in issue
    assert 'hidden-token' not in issue and 'hidden-secret' not in issue and 'A'*35 not in issue
    assert transport.target('a'*32) is None


def test_status_reports_all_local_blockers_without_writes_or_secrets(setup_db,monkeypatch):
    conn,users,_=setup_db;user=users[0]
    monkeypatch.delenv('CSS_APPRISE_TELEGRAM_ENABLED',raising=False)
    before=conn.total_changes
    status=channels.status(conn,user,None)
    assert not status['ready'] and status['can_open_setup'] and len(status['blockers'])==5
    assert conn.total_changes==before and status['binding'] is None
    assert 'Documents is disabled' in status['blockers'][0]
    assert 'Collaborative work is disabled' in status['blockers'][1]
    channels.save(conn,user,0,'off');pref=channels.preferences(conn,user)
    token='123456:'+('A'*35);chat='123456789'
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',json.dumps({pref['binding']:{'bot_token':token,'chat_id':chat}}))
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_ENABLED','1')
    for key in ('work.enabled','documents.enabled'):st.set_setting(conn,key,'1')
    before=conn.total_changes;status=channels.status(conn,user,'https://office.example')
    assert status['ready'] and not status['blockers'] and conn.total_changes==before
    assert token not in str(status) and chat not in str(status)
    assert not channels.status(conn,users[1],'https://office.example')['can_open_setup']
    st.set_setting(conn,'work.enabled','0')
    status=channels.status(conn,user,'https://office.example')
    assert len(status['blockers'])==1 and 'Collaborative work is disabled' in status['blockers'][0]
    assert not channels.available(conn,pref,'https://office.example')
