"""Synthetic intake contracts; never touches an office Drive."""
import json
import pytest
import documents as d
import documents_intake as intake
import documents_permissions as p
import storage as st
from test_documents import registry


class Drive:
    def __init__(self):
        self.fail=False
        self.calls=[]
    def call(self,action,payload,operation):
        self.calls.append((action,payload,operation))
        if action=='intake_check':
            return {'state':'confirmed','fingerprint':payload['fingerprint']}
        if action=='intake_file':
            if self.fail: raise TimeoutError()
            return {'state':'confirmed','file_id':payload['file_id'],'fingerprint':'filed-version'}
        if action=='extract':
            return {'state':'confirmed','file_id':payload['file_id'],'content_key':payload['content_key'],'fingerprint':payload['fingerprint'],
                    'suggestions':{'subject':'Suggested','role':'admin'},'excerpts':['never store me']}
        if action=='intake_list':
            return {'inbox':'inbox_folder_123','files':[]}
        raise AssertionError(action)


def seed(registry,count=1):
    c,u,unit,path=registry
    intake.configure(c,u[1],{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
    files=[{'id':f'scan_file_{i:06}','name':f'scan {i}.pdf','fingerprint':f'v{i}',
            'content_key':f'checksum{i}','mime_type':'application/pdf','size':10} for i in range(count)]
    intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':files})
    return files


def fields():
    return {'direction':'IN','subject':'Reviewed request','type':'Letter','sender':'Regional Office',
            'received_at':'2026-10-18T09:00','confirmed':'yes'}


def test_discovery_replay_permissions_and_changed_content(registry):
    c,u,unit,path=registry
    files=seed(registry)
    assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM document_sequence').fetchone()[0]==0
    intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':files})
    assert c.execute('SELECT COUNT(*) FROM document_intake').fetchone()[0]==1
    with pytest.raises(p.Denied): intake.list_page(c,u[4])
    item=intake.claim(c,u[1],1,1)
    item=intake.extract(c,u[1],1,item['revision'],Drive())
    assert 'never store me' not in json.dumps(item)
    assert 'role' not in item['suggestions']['suggestions']
    files[0]['content_key']='changed';files[0]['fingerprint']='v2'
    intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':files})
    assert intake.get(c,u[1],1)['suggestions']=={}
    with pytest.raises(d.Conflict): intake.save(c,u[1],1,item['revision'],fields())


def test_registration_atomic_group_retry_filing(registry):
    c,u,unit,path=registry
    seed(registry,2)
    item=intake.claim(c,u[1],1,1)
    drive=Drive()
    doc=intake.register(c,u[1],1,item['revision'],fields(),[(2,1)],drive)
    assert doc['instruction_state']=='pending' and doc['lead_id'] is None
    assert c.execute('SELECT COUNT(*) FROM document_assignment').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM document_file_version').fetchone()[0]==2
    assert intake.register(c,u[1],1,item['revision'],fields(),adapter=drive)['id']==doc['id']
    assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0]==1
    drive.fail=True;intake.file_pending(c,drive)
    assert intake.get(c,u[1],1)['filing_state']=='error'
    operation=intake.get(c,u[1],1)['filing_operation']
    drive.fail=False;intake.file_pending(c,drive)
    assert intake.get(c,u[1],1)['filing_state']=='complete'
    assert [x[2] for x in drive.calls if x[0]=='intake_file' and x[1]['ordinal']==1]==[operation,operation]


def test_claim_cache_and_invalid_registration(registry):
    c,u,unit,path=registry
    seed(registry)
    c.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'records','now')",(u[0]['id'],));c.commit()
    item=intake.claim(c,u[1],1,1)
    with pytest.raises(d.Conflict): intake.claim(c,u[0],1,item['revision'])
    drive=Drive();item=intake.extract(c,u[1],1,item['revision'],drive)
    intake.extract(c,u[1],1,item['revision'],drive)
    assert len(drive.calls)==1
    with pytest.raises(ValueError): intake.register(c,u[1],1,item['revision'],{**fields(),'subject':''},adapter=drive)
    assert c.execute('SELECT COUNT(*) FROM document_sequence').fetchone()[0]==0
    st.set_setting(c,'documents.enabled','0')
    with pytest.raises(ValueError): intake.save(c,u[1],1,item['revision'],fields())


def test_queue_pagination(registry):
    c,u,unit,path=registry;seed(registry,35)
    page,more,counts=intake.list_page(c,u[1])
    assert len(page)==30 and more and counts['waiting']==35
    assert len(intake.list_page(c,u[1],page=2)[0])==5


def test_director_first_instruction_routes_and_grants_access(registry):
    c,u,unit,path=registry;seed(registry)
    item=intake.claim(c,u[1],1,1)
    doc=intake.register(c,u[1],1,item['revision'],fields(),adapter=Drive())
    payload={'lead_id':u[0]['id'],'unit_id':unit,'reason':'Evaluate and prepare a recommendation.',
             f"recipient:{u[3]['id']}":'yes','action_due':'2026-10-20'}
    with pytest.raises(p.Denied): d.mutate(c,u[1],doc['id'],doc['revision'],'route_instruction',payload)
    with pytest.raises(ValueError): d.mutate(c,u[1],doc['id'],doc['revision'],'assign',{'user_id':u[0]['id'],'task':'Premature'})
    assert d.list_visible(c,u[1],queue='instruction')==[]
    assert [x['id'] for x in d.list_visible(c,u[2],queue='instruction')]==[doc['id']]
    routed=d.mutate(c,u[2],doc['id'],doc['revision'],'route_instruction',payload)
    assert routed['instruction_state']=='issued' and routed['lead_id']==u[0]['id']
    assert p.can_view(c,u[3],routed)
    assert c.execute('SELECT COUNT(*) FROM document_instruction_recipient').fetchone()[0]==2
    assert c.execute('SELECT COUNT(*) FROM document_assignment').fetchone()[0]==2
    assert d.list_visible(c,u[2],queue='instruction')==[]
    with pytest.raises(d.Conflict): d.mutate(c,u[2],doc['id'],doc['revision'],'route_instruction',payload)


def test_registered_intake_respects_later_restricted_access(registry):
    c,u,unit,path=registry;seed(registry)
    item=intake.claim(c,u[1],1,1)
    doc=intake.register(c,u[1],1,item['revision'],fields(),adapter=Drive())
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],));c.commit()
    assert intake.list_page(c,u[1],'registered')[0]==[]
    assert intake.list_page(c,u[1],'registered')[2].get('registered',0)==0
    with pytest.raises(p.Denied): intake.get(c,u[1],1)


def test_http_intake_review_csrf_and_registration(app_mod,admin,viewer,monkeypatch):
    import documents_operations as ops
    from test_documents_routes import token
    c=st.connect(app_mod.DB);st.init_db(c)
    user=st.get_admin_user(c,'admin@test.local')
    old=st.get_setting(c,'documents.enabled','0')
    try:
        for role in ('records','workflow_admin'):
            c.execute('INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)',(user['id'],role,'intake-test'))
        c.commit();st.set_setting(c,'documents.enabled','1')
        intake.configure(c,user,{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
        intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':[{'id':'http_scan_123456','name':'Letter.pdf',
            'mime_type':'application/pdf','fingerprint':'http-v1','content_key':'http-md5','size':100}]})
        iid=c.execute("SELECT id FROM document_intake WHERE file_id='http_scan_123456'").fetchone()[0]
        monkeypatch.setattr(ops,'get_adapter',lambda:Drive())
        assert viewer.get('/documents/intake').status_code==403
        page=admin.get('/documents/intake');assert page.status_code==200,page.text
        assert 'Letter.pdf' in page.text
        url='/documents/intake/'+str(iid)
        assert admin.post(url,data={'action':'claim','revision':1}).status_code==403
        review=admin.get(url);csrf=token(review)
        claimed=admin.post(url,data={'csrf':csrf,'action':'claim','revision':1})
        assert claimed.status_code==200,claimed.text
        assert 'Original scan preview' in claimed.text
        item=intake.get(c,user,iid)
        extracted=admin.post(url,data={**fields(),'csrf':csrf,'revision':item['revision'],'action':'extract'})
        assert extracted.status_code==200,extracted.text
        assert 'Suggested' in extracted.text
        assert 'Read scan again with OCR' in extracted.text
        item=intake.get(c,user,iid)
        reread=admin.post(url,data={**fields(),'csrf':csrf,'revision':item['revision'],'action':'reread'})
        assert reread.status_code==200,reread.text
        assert 'Suggested' in reread.text
        item=intake.get(c,user,iid)
        registered=admin.post(url,data={**fields(),'csrf':csrf,'revision':item['revision'],'action':'register'})
        assert registered.status_code==200,registered.text
        assert 'Waiting for the Director' in registered.text
        assert 'Drive filing is pending' in registered.text
    finally:
        c.execute("DELETE FROM document_role_grant WHERE created_at='intake-test'")
        c.commit();st.set_setting(c,'documents.enabled',old)
        st.set_setting(c,'documents.drive_intake_enabled','0');c.close()


def test_source_change_during_registration_consumes_no_number(registry):
    c,u,unit,path=registry;files=seed(registry)
    item=intake.claim(c,u[1],1,1)
    class ChangingDrive(Drive):
        def call(self,action,payload,operation):
            assert not c.in_transaction
            files[0]['content_key']='replacement';files[0]['fingerprint']='new-version'
            intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':files})
            return super().call(action,payload,operation)
    with pytest.raises(d.Conflict): intake.register(c,u[1],1,item['revision'],fields(),adapter=ChangingDrive())
    assert c.execute('SELECT COUNT(*) FROM document_sequence').fetchone()[0]==0
    assert intake.get(c,u[1],1)['state']=='attention'


def test_dismiss_restore_and_shared_work_director_gate(registry):
    import work
    c,u,unit,path=registry;seed(registry)
    item=intake.claim(c,u[1],1,1)
    dismissed=intake.save(c,u[1],1,item['revision'],{'note':'Duplicate scan'},'dismiss')
    intake.requeue(c,u[1],1,dismissed['revision'])
    item=intake.claim(c,u[1],1,intake.get(c,u[1],1)['revision'])
    doc=intake.register(c,u[1],1,item['revision'],fields(),adapter=Drive())
    st.set_setting(c,'work.enabled','1')
    with pytest.raises(ValueError,match='Director'):
        work.create(c,u[1],{'title':'Early work','outcome':'Premature assignment','unit_id':unit,'source_document_id':doc['id']})
    assert not c.execute('SELECT 1 FROM work_case').fetchone()
    cancelled=d.mutate(c,u[1],doc['id'],doc['revision'],'cancel',{'reason':'Withdrawn'})
    reopened=d.mutate(c,u[1],doc['id'],cancelled['revision'],'reopen',{'reason':'Received again','due_date':'2026-11-01'})
    assert reopened['instruction_state']=='pending'


def test_poll_failure_and_reviewer_revocation(registry):
    c,u,unit,path=registry;seed(registry)
    class Unavailable(Drive):
        def call(self,*args): raise TimeoutError('private upstream error')
    intake.sync(c,Unavailable())
    assert 'private upstream error' not in intake.settings(c)['sync_error']
    assert c.execute('SELECT COUNT(*) FROM document_intake').fetchone()[0]==1
    item=intake.claim(c,u[1],1,1)
    class RevokingDrive(Drive):
        def call(self,*args):
            c.execute("UPDATE document_role_grant SET revoked_at='now' WHERE user_id=? AND role='records'",(u[1]['id'],));c.commit()
            return super().call(*args)
    with pytest.raises(p.Denied): intake.extract(c,u[1],1,item['revision'],RevokingDrive())
    assert c.execute('SELECT suggestions_json FROM document_intake').fetchone()[0]=='{}'


@pytest.mark.parametrize('code',['unauthorized','unknown_action','not_configured','bad_folder','receipt_mismatch','no_json','unexpected_redirect'])
def test_sync_surfaces_connection_diagnostic_and_retains_queue(registry,code):
    from documents_workspace import WorkspaceError
    c,u,unit,path=registry;seed(registry)
    class RejectingDrive(Drive):
        def call(self,*args):raise WorkspaceError(code,'private provider response / credential')
    intake.sync(c,RejectingDrive())
    error=intake.settings(c)['sync_error']
    assert '['+code+']' in error
    assert 'private provider' not in error and 'credential' not in error
    assert c.execute('SELECT COUNT(*) FROM document_intake').fetchone()[0]==1
    intake.sync(c,Drive())
    assert intake.settings(c)['sync_error']==''
    assert intake.settings(c)['last_sync']


def test_unknown_listing_failure_does_not_expose_provider_text(registry):
    c,u,unit,path=registry;seed(registry)
    class InvalidListing(Drive):
        def call(self,*args):return {'inbox':'another_folder','files':[],'provider_text':'private content'}
    intake.sync(c,InvalidListing())
    assert '[listing]' in intake.settings(c)['sync_error']
    assert 'private content' not in intake.settings(c)['sync_error']


def test_sync_missing_runtime_configuration_is_actionable(registry):
    from documents_workspace import Unconfigured
    c,u,unit,path=registry;seed(registry)
    class MissingConfiguration(Drive):
        def call(self,*args):raise Unconfigured('private credential details')
    intake.sync(c,MissingConfiguration())
    error=intake.settings(c)['sync_error']
    assert '[relay_not_configured]' in error and 'CSS_DOCS_RELAY_URL' in error
    assert 'private credential details' not in error


def test_http_failure_diagnostic_excludes_request_url_and_response_body(registry):
    import httpx
    c,u,unit,path=registry;seed(registry)
    class Forbidden(Drive):
        def call(self,*args):
            response=httpx.Response(403,content=b'private response',request=httpx.Request('POST','https://private.example/secret'))
            response.raise_for_status()
    intake.sync(c,Forbidden())
    error=intake.settings(c)['sync_error']
    assert 'HTTP 403' in error and '[relay_http]' in error
    assert 'private' not in error and 'secret' not in error


@pytest.mark.parametrize('kind,code',[
    ('dns','relay_dns'),('certificate','relay_tls_certificate'),('tls','relay_tls'),
    ('proxy','relay_proxy'),('route','relay_network_route'),('refused','relay_connection_refused'),
    ('reset','relay_connection_reset'),('protocol','relay_remote_protocol'),
    ('local','relay_local_protocol'),('connect','relay_connect'),('read','relay_read'),('write','relay_write')])
def test_network_diagnostic_classifies_cause_without_sensitive_text(registry,kind,code):
    import errno,socket,ssl,httpx
    c,u,unit,path=registry;seed(registry)
    request=httpx.Request('POST','https://script.google.com/macros/s/private-endpoint/exec')
    classes={'proxy':httpx.ProxyError,'protocol':httpx.RemoteProtocolError,'local':httpx.LocalProtocolError,
             'read':httpx.ReadError,'write':httpx.WriteError}
    exc=classes.get(kind,httpx.ConnectError)('private credential and proxy details',request=request)
    causes={'dns':socket.gaierror(-2,'private DNS details'),
            'certificate':ssl.SSLCertVerificationError(1,'private certificate details'),
            'tls':ssl.SSLError(1,'private TLS details'),
            'route':OSError(errno.ENETUNREACH,'private network details'),
            'refused':OSError(errno.ECONNREFUSED,'private network details'),
            'reset':OSError(errno.ECONNRESET,'private network details')}
    if kind in causes:exc.__cause__=causes[kind]
    class NetworkFailure(Drive):
        def call(self,*args):raise exc
    intake.sync(c,NetworkFailure())
    error=intake.settings(c)['sync_error']
    assert '['+code+']' in error
    assert 'private' not in error and 'credential' not in error
    assert c.execute('SELECT COUNT(*) FROM document_intake').fetchone()[0]==1


def test_network_diagnostic_identifies_reply_host_and_message_only_certificate_error():
    import httpx
    exc=httpx.ConnectError('[SSL: CERTIFICATE_VERIFY_FAILED] private proxy data',
        request=httpx.Request('GET','https://script.googleusercontent.com/private-token'))
    error=intake.sync_failure(exc,'relay')
    assert 'reply service' in error and '[relay_tls_certificate]' in error
    assert 'private' not in error and 'token' not in error


def test_ocr_metadata_drift_updates_fingerprint_without_changing_content(registry):
    c,u,unit,path=registry;seed(registry)
    item=intake.claim(c,u[1],1,1)
    class MetadataOnly(Drive):
        def call(self,action,payload,operation):
            assert action=='extract' and payload['intake'] is True
            assert payload['inbox']=='inbox_folder_123' and payload['content_key']==item['content_key']
            return {**super().call(action,payload,operation),'fingerprint':'latest-metadata-version'}
    saved=intake.extract(c,u[1],1,item['revision'],MetadataOnly())
    assert saved['fingerprint']=='latest-metadata-version' and saved['content_key']==item['content_key']
    assert saved['suggestions']['suggestions']['subject']=='Suggested'


@pytest.mark.parametrize('mode',['old_relay','wrong_file','changed_content'])
def test_ocr_requires_content_receipt_before_caching(registry,mode):
    c,u,unit,path=registry;seed(registry)
    item=intake.claim(c,u[1],1,1)
    class UnconfirmedSource(Drive):
        def call(self,*args):
            result=super().call(*args)
            if mode=='old_relay':result.pop('content_key')
            elif mode=='wrong_file':result['file_id']='other_file_1234'
            else:result['content_key']='replacement content'
            return result
    with pytest.raises(ValueError):intake.extract(c,u[1],1,item['revision'],UnconfirmedSource())
    assert intake.get(c,u[1],1)['suggestions']=={}


def test_explicit_ocr_reread_refreshes_suggestions_without_overwriting_draft(registry):
    c,u,unit,path=registry
    seed(registry)
    item=intake.claim(c,u[1],1,1)
    item=intake.save(c,u[1],1,item['revision'],fields())
    drive=Drive()
    item=intake.extract(c,u[1],1,item['revision'],drive)
    intake.extract(c,u[1],1,item['revision'],drive)
    assert len(drive.calls)==1

    class Improved(Drive):
        def call(self,action,payload,operation):
            result=super().call(action,payload,operation)
            result['suggestions'].update(document_date='2026-10-15',type='Memorandum',sender='BLHSD')
            return result

    fresh=Improved()
    item=intake.extract(c,u[1],1,item['revision'],fresh,force=True)
    assert len(fresh.calls)==1
    assert item['suggestions']['suggestions']['document_date']=='2026-10-15'
    assert item['suggestions']['suggestions']['type']=='Memorandum'
    assert item['draft']['subject']=='Reviewed request'
    assert item['draft']['type']=='Letter'


@pytest.mark.parametrize('sender,expected',[
    ('Bureau of Local Health Systems Development - Office of the Director','OUT'),
    ('BUREAU OF LOCAL HEALTH SYSTEMS DEVELOPMENT (BLHSD)','OUT'),
    ('BLHSD - Health Systems Development Division (HSDD)','OUT'),
    ('blhsd@doh.gov.ph','OUT'),
    ('Regional Office','IN'),('OtherBLHSDOffice','IN'),('', ''),
])
def test_direction_from_originating_office(sender,expected):
    assert intake.direction_from_sender(sender)==expected


def test_cached_ocr_direction_and_reviewed_sender_rule(registry):
    c,u,unit,path=registry;seed(registry)
    item=intake.claim(c,u[1],1,1)
    c.execute("UPDATE document_intake SET suggestions_json=? WHERE id=1",
              (json.dumps({'suggestions':{'sender':'BLHSD - HSDD'},'warnings':[]}),))
    c.commit()
    assert intake.get(c,u[1],1)['suggestions']['suggestions']['direction']=='OUT'
    saved=intake.save(c,u[1],1,item['revision'],{**fields(),'sender':'BLHSD','direction':'IN'})
    assert saved['draft']['direction']=='OUT'
    doc=intake.register(c,u[1],1,saved['revision'],{**fields(),'sender':'BLHSD','direction':'IN'},adapter=Drive())
    assert doc['direction']=='OUT'
    assert doc['instruction_state']=='not_required'


def test_corrected_sender_recalculates_direction():
    assert intake.clean_fields({'sender':'Regional Office','direction':'OUT'})['direction']=='IN'
    assert intake.clean_fields({'sender':'BLHSD','direction':'IN'})['direction']=='OUT'
    assert intake.clean_fields({'sender':'','direction':''})['direction']==''
