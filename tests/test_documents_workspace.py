"""Existing Workspace protocol compatibility and actual Apps Script contracts."""
import hashlib
import hmac
import json
import pathlib
import shutil
import subprocess
import httpx
import pytest
import documents_workspace as ws

ROOT=pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def relay_env(monkeypatch):
    for prefix in ('CSS_DOCS_RELAY','CSS_MAIL_RELAY'):
        monkeypatch.setenv(prefix+'_URL','https://script.google.com/macros/s/'+prefix+'/exec')
        monkeypatch.setenv(prefix+'_SECRET',prefix+'-test-secret')


def transport(monkeypatch,handler):
    real=httpx.Client
    monkeypatch.setattr(ws.httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))


@pytest.mark.parametrize('action,kind,prefix',[('inspect',None,'CSS_DOCS_RELAY'),('sign',None,'CSS_DOCS_RELAY'),('dispatch',None,'CSS_MAIL_RELAY'),('status','dispatch','CSS_MAIL_RELAY'),('status','sign','CSS_DOCS_RELAY')])
def test_existing_credentials_ms_envelope_and_reply_get(relay_env,monkeypatch,action,kind,prefix):
    requests=[]
    def handle(request):
        requests.append(request)
        if request.method=='POST':
            env=json.loads(request.content)
            assert set(env)=={'ts','payload','sig'}
            assert env['ts']>10**12
            assert env['sig']==hmac.new((prefix+'-test-secret').encode(),f"{env['ts']}.{env['payload']}".encode(),hashlib.sha256).hexdigest()
            assert json.loads(env['payload'])['action']=='document_'+action
            assert prefix in str(request.url)
            return httpx.Response(302,headers={'Location':'https://script.googleusercontent.com/macros/echo?test=result'})
        assert not request.content
        return httpx.Response(200,json={'ok':True,'operation_id':'op','state':'confirmed'})
    transport(monkeypatch,handle)
    assert ws.WorkspaceRelay().call(action,{'kind':kind,'actor_id':1},'op')['state']=='confirmed'
    assert [r.method for r in requests]==['POST','GET']


def test_timeout_never_repeats_post(relay_env,monkeypatch):
    calls=[]
    def handle(req):
        calls.append(req);raise httpx.ReadTimeout('timeout')
    transport(monkeypatch,handle)
    with pytest.raises(httpx.ReadTimeout):ws.WorkspaceRelay().call('dispatch',{},'op')
    assert len(calls)==1


@pytest.mark.parametrize('destination',['https://evil.test/collect','http://script.googleusercontent.com/result','https://script.google.com/macros/s/other/exec'])
def test_never_forwards_signed_payload_to_a_redirect(relay_env,monkeypatch,destination):
    calls=[]
    def handle(req):
        calls.append(req);return httpx.Response(302,headers={'Location':destination})
    transport(monkeypatch,handle)
    with pytest.raises(ValueError,match='redirect'):ws.WorkspaceRelay().call('sign',{},'op')
    assert len(calls)==1


def test_unconfirmed_legacy_reply_is_not_official_send_success(relay_env,monkeypatch):
    transport(monkeypatch,lambda req:httpx.Response(200,json={'ok':True}))
    with pytest.raises(ValueError,match='deployed relay'):ws.WorkspaceRelay().call('dispatch',{},'op')


def test_bounded_response(relay_env,monkeypatch):
    transport(monkeypatch,lambda req:httpx.Response(200,content=b'x'*(ws.MAX_RESPONSE+1)))
    with pytest.raises(ValueError,match='metadata limit'):ws.WorkspaceRelay().call('extract',{},'op')


@pytest.mark.skipif(shutil.which('node') is None,reason='Node unavailable')
def test_production_scripts_lifecycle_and_mail_compatibility():
    result=subprocess.run(['node','tests/js/documents_relay_harness.js'],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['passed']


@pytest.mark.parametrize('name',['documents_relay.gs','mail_relay.gs'])
def test_new_scripts_parse(name,tmp_path):
    if shutil.which('node') is None:pytest.skip('Node unavailable')
    path=tmp_path/(name+'.js');path.write_text((ROOT/'apps_script'/name).read_text())
    result=subprocess.run(['node','--check',str(path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('code',['unauthorized','unknown_action'])
def test_relay_rejection_before_operation_has_specific_safe_code(relay_env,monkeypatch,code):
    transport(monkeypatch,lambda req:httpx.Response(200,json={'ok':False,'error':code}))
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.WorkspaceRelay().call('intake_list',{'inbox':'private-folder','actor_id':1},'expected-op')
    assert caught.value.code==code


def test_rejection_with_wrong_operation_stays_mismatched(relay_env,monkeypatch):
    transport(monkeypatch,lambda req:httpx.Response(200,json={'ok':False,'operation_id':'other','error':'unauthorized'}))
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.WorkspaceRelay().call('intake_list',{'actor_id':1},'expected-op')
    assert caught.value.code=='receipt_mismatch'


def test_unknown_provider_text_never_becomes_diagnostic_code(relay_env,monkeypatch):
    transport(monkeypatch,lambda req:httpx.Response(200,json={'ok':False,'operation_id':'op','error':'private provider response / secret value'}))
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.WorkspaceRelay().call('intake_list',{'actor_id':1},'op')
    assert caught.value.code=='unconfirmed'
    assert 'private provider' not in str(caught.value)
