"""Real staged-pilot isolation and allowlisted webhook intake; no provider traffic."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import httpx
import pytest
from datetime import datetime, timezone
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings():
    return {'OFFICE_TELEGRAM_PILOT_PASSWORDS':json.dumps({x:secrets.token_urlsafe(24) for x in ('staff','officer','peer','admin')}),
            'OFFICE_TELEGRAM_PILOT_SENDERS':'[123456789]', 'CSS_TELEGRAM_BOT_TOKEN':'123456:synthetic_test_token_1234567890',
            'CSS_TELEGRAM_WEBHOOK_SECRET':'S'*40, 'CSS_SESSION_SECRET':'K'*48,
            'OFFICE_TELEGRAM_PILOT_BATCH':'A'}


@pytest.mark.parametrize('field,value', [
    ('OFFICE_TELEGRAM_PILOT_PASSWORDS','{}'), ('OFFICE_TELEGRAM_PILOT_SENDERS','[]'),
    ('OFFICE_TELEGRAM_PILOT_SENDERS','[true]'), ('OFFICE_TELEGRAM_PILOT_SENDERS','[1,1]'),
    ('CSS_TELEGRAM_BOT_TOKEN','bad'), ('CSS_TELEGRAM_WEBHOOK_SECRET','short'),
    ('CSS_SESSION_SECRET',''), ('OFFICE_TELEGRAM_PILOT_BATCH','groups'),
    ('SPACE_HOST','equityinhealth-office-connect.hf.space'),
])
def test_configuration_fails_closed_without_values_in_error(field,value):
    pilot=script('telegram_pilot_app');env=settings();env[field]=value
    with pytest.raises(ValueError,match='configuration missing or invalid') as error:
        pilot.configuration(env)
    assert str(error.value)=='Pilot configuration missing or invalid; check the documented secret names.'


def test_boundary_authenticates_before_body_and_never_forwards_unlisted_or_stale():
    pilot=script('telegram_pilot_app');config=pilot.configuration(settings());seen=[]
    async def app(scope,receive,send):
        seen.append(await receive())
        await JSONResponse({'accepted':True})(scope,receive,send)
    started=int(time.time())-10
    client=TestClient(pilot.PilotBoundary(app,config,{'source_commit':'f'*40,'version':'9.91'},started=started))
    path=pilot.WEBHOOK
    packet={'update_id':1,'message':{'message_id':1,'date':int(time.time()),'from':{'id':123456789,'is_bot':False},
                                   'chat':{'id':123456789,'type':'private'},'text':'/start'}}
    headers={'X-Telegram-Bot-Api-Secret-Token':'S'*40}
    assert client.post(path,content=b'not json').status_code==403
    assert client.post(path,json=packet,headers={**headers,'X-Telegram-Bot-Api-Secret-Token':'wrong'}).status_code==403
    assert client.post(path,content=b'x'*65537,headers=headers).status_code==413
    for update in (
        {'message':{**packet['message'],'from':{'id':99,'is_bot':False}}},
        {'message':{**packet['message'],'chat':{'id':-1,'type':'group'}}},
        {'message':{**packet['message'],'message_thread_id':1}},
        {'callback_query':{'from':{'id':123456789}}},
    ):
        assert client.post(path,json=update,headers=headers).status_code in (400,403)
    stale={**packet,'message':{**packet['message'],'date':started}}
    assert client.post(path,json=stale,headers=headers).json()=={'ok':True}
    assert not seen
    assert client.post(path,json=packet,headers=headers).json()=={'accepted':True}
    assert json.loads(seen[0]['body'])==packet
    health=client.get('/pilot-health').json()
    assert health['disposable'] and health['batch']=='A' and health['boot_id']
    assert 'senders' not in health


def test_publisher_rejects_wrong_or_nonprotected_target_and_missing_secrets():
    deploy=script('deploy_telegram_pilot_hf')
    good=SimpleNamespace(id=deploy.TARGET,visibility='protected',private=True,sdk='docker')
    deploy.verify_target(good,deploy.REQUIRED_SECRETS)
    for changes in ({'id':'equityinhealth/office-connect'}, {'visibility':'private'}, {'visibility':'public'}, {'private':False}):
        with pytest.raises(ValueError):deploy.verify_target(SimpleNamespace(**{**vars(good),**changes}),deploy.REQUIRED_SECRETS)
    with pytest.raises(ValueError,match='Missing pilot secrets'):deploy.verify_target(good,[])


def test_actual_bundle_seed_isolation_and_phone_link(tmp_path):
    deploy=script('deploy_telegram_pilot_hf');pilot=script('telegram_pilot_app')
    bundle=tmp_path/'bundle';bundle.mkdir();manifest=deploy.stage(bundle)
    assert manifest['target']==deploy.TARGET
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((bundle/name).read_bytes()).hexdigest()==digest
    assert not list(bundle.rglob('*.db')) and not (bundle/'deploy_hf.py').exists()
    assert not (bundle/'preview-build.json').exists()
    sentinel=tmp_path/'untouched.db';sentinel.write_bytes(b'synthetic sentinel')
    env=dict(os.environ, **settings())
    passwords=json.loads(env['OFFICE_TELEGRAM_PILOT_PASSWORDS'])
    env.update(CSS_DB=str(sentinel),CSS_PERSIST_DIR=str(tmp_path/'do-not-create'),
               CSS_SMTP_HOST='forbidden.invalid',CSS_MAIL_RELAY_URL='https://forbidden.invalid',
               CSS_TELEGRAM_GROUPS_ENABLED='1',HF_TOKEN='fake-inherited-token',SPACE_HOST=pilot.TARGET_HOST)
    log_path=tmp_path/'pilot.log'
    with log_path.open('w') as log:
        process=subprocess.Popen([sys.executable,str(bundle/'scripts/telegram_pilot_app.py')],cwd=bundle,
            env=env,stdout=log,stderr=log,start_new_session=True)
        try:
            with httpx.Client(base_url='http://127.0.0.1:7860',trust_env=False) as client:
                for _ in range(180):
                    assert process.poll() is None,log_path.read_text()
                    try:
                        response=client.get('/pilot-health')
                        if response.status_code==200:break
                    except httpx.TransportError:pass
                    time.sleep(.25)
                else:pytest.fail('Pilot startup timed out')
                health=response.json();assert health['source_commit']==manifest['source_commit']
                assert health['version']==manifest['version'] and health['batch']=='A'
                assert 'TELEGRAM PILOT' in client.get('/login').text
                assert 'Set up the first account' not in client.get('/login').text
                assert client.get('/me').status_code in (302,303)
                assert client.get('/pilot-fixtures').status_code==303
                assert client.post(pilot.WEBHOOK,json={}).status_code==403
            # Real Chromium with canonical HTTPS origin routed only to loopback.
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
                origin='https://'+pilot.TARGET_HOST
                def route(request):
                    with httpx.Client(trust_env=False) as local:
                        result=local.request(request.request.method,request.request.url.replace(origin,'http://127.0.0.1:7860'),
                            content=request.request.post_data_buffer,headers={**request.request.headers,'host':pilot.TARGET_HOST})
                    request.fulfill(status=result.status_code,headers={k:v for k,v in result.headers.items() if k not in ('content-encoding','content-length')},body=result.content)
                context.route(origin+'/**',route)
                page=context.new_page()
                page.goto(origin+'/login')
                page.locator('[name=username]').fill('pilot-staff@example.invalid')
                page.locator('[name=password]').fill(passwords['staff'])
                page.locator('button[type=submit]').click()
                page.wait_for_url(lambda u:'/login' not in u)
                page.goto(origin+'/pilot-fixtures')
                assert 'restricted_document' in page.locator('body').inner_text()
                page.goto(origin+'/account/telegram')
                assert 'Read permitted calendar entries' in page.locator('body').inner_text()
                import re
                headers={'X-Telegram-Bot-Api-Secret-Token':'S'*40,'Host':pilot.TARGET_HOST}
                def command(number,text):
                    return httpx.post('http://127.0.0.1:7860'+pilot.WEBHOOK,trust_env=False,headers=headers,
                        json={'update_id':number,'message':{'message_id':number,'date':int(datetime.now(timezone.utc).timestamp()),
                            'from':{'id':123456789,'is_bot':False},'chat':{'id':123456789,'type':'private'},'text':text}}).json()
                packet=command(1,'/start');assert 'text' in packet,packet
                code=re.search(r'(?m)^[a-f0-9]{64}$',packet['text'])[0]
                page.get_by_label('Read permitted calendar entries').check()
                page.get_by_label('Private linking code').fill(code)
                page.get_by_label('Link this Office Connect account to my own private Telegram account.').check()
                page.get_by_role('button',name='Request confirmation in Telegram').click()
                packet=command(2,'/status');confirmation=re.search(r'/confirm [a-f0-9]{64}',packet['text'])[0]
                assert 'sendMessage'==command(3,confirmation)['method']
                assert 'PILOT plain meeting' in command(4,'/calendar')['text']
                assert 'method' not in command(4,'/calendar')
                assert '/my_tasks' not in command(5,'/menu')['text']
                context.close();browser.close()
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGINT)
            process.wait(timeout=20)
    assert sentinel.read_bytes()==b'synthetic sentinel'
    assert not (tmp_path/'do-not-create').exists()


def test_pilot_environment_drops_inherited_providers_and_only_enables_selected_batch(monkeypatch,tmp_path):
    pilot=script('telegram_pilot_app')
    from telegram_storage import SWITCHES
    for batch in ('off','A','B','C','D','E','F'):
        env={**settings(),'OFFICE_TELEGRAM_PILOT_BATCH':batch,'CSS_PERSIST_DIR':'forbidden',
             'CSS_SMTP_HOST':'forbidden','CSS_MAIL_RELAY_SECRET':'forbidden',
             'HF_TOKEN':'forbidden','CSS_TELEGRAM_GROUPS_ENABLED':'1','CSS_TEST_NOW':'1999-01-01'}
        config=pilot.configuration(env)
        with monkeypatch.context() as patch:
            patch.setattr(os,'environ',env)
            pilot.isolate(config,tmp_path/'synthetic.db')
            assert not {'HF_TOKEN','CSS_PERSIST_DIR','CSS_SMTP_HOST','CSS_MAIL_RELAY_SECRET','CSS_TEST_NOW'} & env.keys()
            assert env['CSS_NO_SCHEDULER']=='1' and env['CSS_APPRISE_TELEGRAM_ENABLED']=='0'
            assert env['CSS_TELEGRAM_REPLY_TRANSPORT']=='webhook'
            enabled={x for x in SWITCHES if env['CSS_TELEGRAM_'+x.upper()+'_ENABLED']=='1'}
            assert enabled==(set(pilot.BASE+pilot.BATCHES[batch]) if batch!='off' else set())
            assert not {'groups','reminders','change_notices'} & enabled


def test_native_fixtures_keep_roles_ownership_and_source_visibility(tmp_path):
    import storage as st
    import work
    import work_tasks
    import documents_permissions
    import supplies_requests
    database=tmp_path/'native-pilot.db'
    seed=script('telegram_pilot_seed').seed
    passwords=json.loads(settings()['OFFICE_TELEGRAM_PILOT_PASSWORDS'])
    fixtures=seed(database,passwords)
    conn=st.connect(str(database))
    try:
        staff=st.get_admin_user(conn,'pilot-staff@example.invalid')
        officer=st.get_admin_user(conn,'pilot-officer@example.invalid')
        admin=st.get_admin_user(conn,'pilot-admin@example.invalid')
        assert staff['role']=='viewer' and officer['role']=='viewer' and staff['rp_id']
        case=work.get(conn,staff,fixtures['work'])
        assert not work.officer(conn,staff,case) and work.officer(conn,officer,case)
        with pytest.raises(documents_permissions.Denied):work.get(conn,staff,fixtures['restricted_work'])
        assert {t['status'] for t in work_tasks.list_for_case(conn,staff,case['id'])}=={
            'proposed','todo','in_progress','for_review','done','cancelled'}
        own=supplies_requests._owned(conn,staff,fixtures['supply_drafts']['staff'])
        assert own['approval_status']=='draft' and own['control_number'] is None
        with pytest.raises(ValueError):supplies_requests._owned(conn,staff,fixtures['supply_drafts']['peer'])
        import rooms
        assert rooms.is_room_admin(conn,admin) and not rooms.is_room_admin(conn,officer)
        assert supplies_requests._owned(conn,staff,fixtures['supply_drafts']['returned'])['approval_status']=='returned'
        assert fixtures['personal']['staff']['travel'] != fixtures['personal']['peer']['travel']
        assert st.count_admin_users(conn)==4
        assert not conn.execute('SELECT 1 FROM telegram_connection').fetchone()
        assert not conn.execute('SELECT 1 FROM telegram_grant').fetchone()
        with pytest.raises(ValueError,match='empty database'):seed(database,passwords)
        assert st.count_admin_users(conn)==4
    finally:
        conn.close()
