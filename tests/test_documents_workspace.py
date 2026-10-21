"""Existing Workspace protocol compatibility and actual Apps Script contracts."""
import hashlib
import hmac
import json
import pathlib
import shutil
import subprocess
from types import SimpleNamespace
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


@pytest.mark.parametrize('encoding',['gzip','deflate'])
def test_compressed_google_reply_is_decoded_once(relay_env,monkeypatch,encoding):
    import gzip,zlib
    calls=[]
    data={'ok':True,'operation_id':'op','inbox':'office_folder_123','files':[]}
    raw=json.dumps(data).encode()
    compressed=gzip.compress(raw) if encoding=='gzip' else zlib.compress(raw)
    def handle(request):
        calls.append(request)
        if request.method=='POST':
            return httpx.Response(302,headers={'Location':'https://script.googleusercontent.com/macros/echo?result=private'})
        assert not request.content
        return httpx.Response(200,headers={'Content-Encoding':encoding,'Content-Length':str(len(compressed)),
            'Content-Type':'application/json'},stream=httpx.ByteStream(compressed))
    transport(monkeypatch,handle)
    assert ws.WorkspaceRelay().call('intake_list',{'inbox':'office_folder_123','actor_id':1},'op')==data
    assert [r.method for r in calls]==['POST','GET']


def test_decoded_metadata_limit_applies_to_compressed_response(relay_env,monkeypatch):
    import gzip
    compressed=gzip.compress(b'x'*(ws.MAX_RESPONSE+1))
    transport(monkeypatch,lambda req:httpx.Response(200,headers={'Content-Encoding':'gzip'},stream=httpx.ByteStream(compressed)))
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.WorkspaceRelay().call('intake_list',{'actor_id':1},'op')
    assert caught.value.code=='response_too_large'


def test_redirect_uses_remaining_call_budget_and_explicit_phase_timeouts(relay_env, monkeypatch):
    clock, calls = [0.0], []
    monkeypatch.setattr(ws, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    def handle(request):
        calls.append((request.method, request.extensions['timeout']))
        if request.method == 'POST':
            clock[0] = ws.CALL_SECONDS - 1
            return httpx.Response(302, headers={'Location': 'https://script.googleusercontent.com/result'})
        return httpx.Response(200, json={'ok': True, 'operation_id': 'op', 'state': 'confirmed'})
    transport(monkeypatch, handle)
    assert ws.WorkspaceRelay().call('dispatch', {}, 'op')['state'] == 'confirmed'
    assert [method for method, _ in calls] == ['POST', 'GET']
    assert calls[0][1] == {'connect': 10, 'read': 90, 'write': 90, 'pool': 10}
    assert calls[1][1] == {'connect': 1, 'read': 1, 'write': 1, 'pool': 1}


def test_exhausted_call_budget_does_not_follow_redirect_or_repeat_post(relay_env, monkeypatch):
    clock, calls = [0.0], []
    monkeypatch.setattr(ws, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    def handle(request):
        calls.append(request.method)
        clock[0] = ws.CALL_SECONDS + 1
        return httpx.Response(302, headers={'Location': 'https://script.googleusercontent.com/result'})
    transport(monkeypatch, handle)
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.WorkspaceRelay().call('dispatch', {}, 'op')
    assert caught.value.code == 'timeout'
    assert calls == ['POST']


def test_trickled_response_cannot_keep_resetting_the_elapsed_budget(relay_env, monkeypatch):
    clock, calls, closed = [0.0], [], []
    monkeypatch.setattr(ws, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(10):
                clock[0] += ws.CALL_SECONDS / 2 + 1
                yield b' '
        def close(self):
            closed.append(True)
    def handle(request):
        calls.append(request.method)
        return httpx.Response(200, stream=SlowStream())
    transport(monkeypatch, handle)
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.WorkspaceRelay().call('extract', {}, 'op')
    assert caught.value.code == 'timeout'
    assert clock[0] < ws.CALL_SECONDS * 2
    assert calls == ['POST'] and closed == [True]
