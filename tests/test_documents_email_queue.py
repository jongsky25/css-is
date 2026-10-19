"""Email and Drive converge without premature numbering or duplicate registration."""
from concurrent.futures import ThreadPoolExecutor
import pytest
import documents as d
import documents_email as email
import documents_intake as intake
import storage as st
from test_documents_email import setup, payload, signed
from test_documents_intake import Drive, fields


def enable(c,uid):
    c.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'workflow_admin','now')",(uid,));c.commit()
    intake.configure(c,{'id':uid},{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})


def metadata():
    return [{'id':a['drive_url'].split('/d/')[1].split('/')[0], 'name':f'attachment {n}.pdf',
             'fingerprint':f'v{n}','content_key':f'md5-{n}','mime_type':'application/pdf','size':100,
             'email_attachment':True} for n,a in enumerate(payload()['attachments'])]


def discover(c,files=None):
    intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':metadata() if files is None else files})


def test_email_waits_for_review_then_registers_group_with_provenance(setup):
    c,path,uid,client=setup;enable(c,uid);user={'id':uid}
    result=signed(client);assert result.status_code==201,result.text
    first=result.json();iid=first['intake_id']
    assert first=={'intake_id':iid,'state':'queued','duplicate':False}
    assert not c.execute('SELECT 1 FROM document_sequence').fetchone()
    assert not c.execute('SELECT 1 FROM document').fetchone()
    page,more,counts=intake.list_page(c,user)
    assert len(page)==1 and counts=={'waiting':1}
    item=intake.get(c,user,iid)
    assert item['draft']['received_at']=='2026-10-17T10:00'
    assert item['draft']['sender']==payload()['sender']
    assert len(item['email_files'])==2
    discover(c)
    item=intake.claim(c,user,iid,intake.get(c,user,iid)['revision'])
    doc=intake.register(c,user,iid,item['revision'],{**item['draft'],'confirmed':'yes'},adapter=Drive())
    assert doc['instruction_state']=='pending'
    assert c.execute('SELECT COUNT(*) FROM document_file_version WHERE document_id=?',(doc['id'],)).fetchone()[0]==2
    receipt=c.execute('SELECT channel,evidence FROM document_receipt WHERE document_id=?',(doc['id'],)).fetchone()
    assert receipt==('gmail','Gmail message '+payload()['message_id'])
    assert c.execute('SELECT received_at FROM document_email_import').fetchone()[0]==payload()['received_at']
    assert signed(client).json()=={**first,'duplicate':True}
    assert len(intake.list_page(c,user,'registered')[0])==1
    intake.file_pending(c,Drive())
    assert c.execute("SELECT COUNT(*) FROM document_intake WHERE filing_state='complete'").fetchone()[0]==2


def test_drive_before_webhook_skips_receipts_and_partial_email_uploads(setup):
    c,path,uid,client=setup;enable(c,uid)
    discover(c,metadata()+[{'id':'receipt_file_123','email_receipt':True}])
    assert not c.execute('SELECT 1 FROM document_intake').fetchone()
    assert signed(client).status_code==201
    discover(c)
    assert c.execute('SELECT COUNT(*) FROM document_intake').fetchone()[0]==2
    assert len(intake.list_page(c,{'id':uid})[0])==1


def test_concurrent_staging_and_changed_payload(setup):
    c,path,uid,client=setup;enable(c,uid)
    def run(_):
        other=st.connect(path)
        try: return email.ingest(other,payload())
        finally: other.close()
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(run,range(4)))
    assert sum(not r['duplicate'] for r in results)==1
    assert len({r['intake_id'] for r in results})==1
    assert signed(client,{**payload(),'subject':'Changed'}).status_code==409
    assert not c.execute('SELECT 1 FROM document').fetchone()


def test_pausing_drive_never_reverts_to_direct_registration(setup):
    c,path,uid,client=setup;enable(c,uid)
    intake.configure(c,{'id':uid},{'inbox':'inbox_folder_123','filed':'filed_folder_123'})
    assert signed(client).json()['state']=='queued'
    assert not c.execute('SELECT 1 FROM document').fetchone()
    st.set_setting(c,'documents.gmail_intake_enabled','0')
    assert signed(client).status_code==403


def test_group_dismiss_restore_and_changed_sibling_invalidates_review(setup):
    c,path,uid,client=setup;enable(c,uid);user={'id':uid}
    iid=signed(client).json()['intake_id'];discover(c)
    item=intake.claim(c,user,iid,intake.get(c,user,iid)['revision'])
    child=item['email_files'][1]
    with pytest.raises(d.Conflict):intake.claim(c,user,child['id'],child['revision'])
    dismissed=intake.save(c,user,iid,item['revision'],{'note':'Unrelated email'},'dismiss')
    assert intake.list_page(c,user)[0]==[]
    assert c.execute("SELECT COUNT(*) FROM document_intake WHERE state='dismissed'").fetchone()[0]==2
    intake.requeue(c,user,iid,dismissed['revision'])
    item=intake.claim(c,user,iid,intake.get(c,user,iid)['revision'])
    changed=metadata();changed[1]['content_key']='new content';changed[1]['fingerprint']='new-v'
    discover(c,changed)
    with pytest.raises(d.Conflict):intake.register(c,user,iid,item['revision'],fields(),adapter=Drive())
    assert not c.execute('SELECT 1 FROM document_sequence').fetchone()


def test_email_cannot_be_split_or_marked_outgoing(setup):
    c,path,uid,client=setup;enable(c,uid);user={'id':uid}
    iid=signed(client).json()['intake_id'];discover(c)
    item=intake.claim(c,user,iid,intake.get(c,user,iid)['revision'])
    with pytest.raises(ValueError,match='Incoming'):intake.register(c,user,iid,item['revision'],{**fields(),'direction':'OUT'},adapter=Drive())
    with pytest.raises(ValueError,match='already grouped'):intake.register(c,user,iid,item['revision'],fields(),[(999,1)],Drive())
    assert not c.execute('SELECT 1 FROM document').fetchone()


def test_office_attachment_can_register_without_ocr(setup):
    c,path,uid,client=setup;enable(c,uid);user={'id':uid}
    iid=signed(client).json()['intake_id']
    files=metadata();files[0]['mime_type']='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    discover(c,files)
    item=intake.claim(c,user,iid,intake.get(c,user,iid)['revision'])
    with pytest.raises(ValueError,match='manually'):intake.extract(c,user,iid,item['revision'],Drive())
    assert intake.register(c,user,iid,item['revision'],fields(),adapter=Drive())['instruction_state']=='pending'


def test_signed_javascript_handoff_queues_in_python(setup):
    import json
    from test_gmail_import_script import harness
    c,path,uid,client=setup;enable(c,uid)
    envelope=json.loads(harness('--envelope'))
    result=client.post(email.PATH,content=envelope['body'].encode(),headers=envelope['headers'])
    assert result.status_code==201,result.text
    assert result.json()['state']=='queued'
    assert not c.execute('SELECT 1 FROM document').fetchone()


@pytest.mark.parametrize('body_only',[False,True])
def test_email_review_screen_registers_group_and_redirects_children(app_mod,admin,monkeypatch,body_only):
    import documents_operations as ops
    from test_documents_routes import token
    c=st.connect(app_mod.DB);st.init_db(c)
    user=st.get_admin_user(c,'admin@test.local')
    keys=['enabled','gmail_intake_enabled','gmail_mailbox','gmail_actor_id','gmail_review_queue_enabled',
          'drive_intake_enabled','drive_inbox','drive_filed','drive_actor_id']
    old={key:st.get_setting(c,'documents.'+key,'') for key in keys}
    try:
        for role in ('records','workflow_admin'):
            c.execute('INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)',(user['id'],role,'email-queue-http'))
        c.commit()
        for key,value in {'enabled':'1','gmail_intake_enabled':'1','gmail_mailbox':'office@example.test','gmail_actor_id':str(user['id'])}.items():
            st.set_setting(c,'documents.'+key,value)
        intake.configure(c,user,{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
        source=payload()
        if body_only:source.update(message_id='19bb123',attachments=[],body_text='Please review.\n<script>alert(1)</script>')
        iid=email.ingest(c,source)['intake_id']
        if not body_only:discover(c)
        item=intake.get(c,user,iid);url='/documents/intake/'+str(iid)
        page=admin.get(url);assert page.status_code==200,page.text
        assert 'Received by office email' in page.text
        if body_only:
            assert 'No attachment' in page.text and '&lt;script&gt;' in page.text
            assert 'Read scan with OCR' not in page.text and '/preview' not in page.text
        else: assert 'All 2 attachments' in page.text
        assert payload()['subject'] in admin.get('/documents/intake').text
        if not body_only:
            child=admin.get('/documents/intake/'+str(item['email_files'][1]['id']),follow_redirects=False)
            assert child.status_code==303 and child.headers['location']==url
        csrf=token(page)
        assert admin.post(url,data={'csrf':csrf,'action':'claim','revision':item['revision']}).status_code==200
        item=intake.get(c,user,iid);monkeypatch.setattr(ops,'get_adapter',lambda:Drive())
        registered=admin.post(url,data={**item['draft'],'confirmed':'yes','csrf':csrf,'revision':item['revision'],'action':'register'})
        assert registered.status_code==200,registered.text
        assert 'Waiting for the Director' in registered.text
        assert c.execute('SELECT COUNT(*) FROM document_file_version WHERE document_id=?',(intake.get(c,user,iid)['document_id'],)).fetchone()[0]==(0 if body_only else 2)
        intake.file_pending(c,Drive())
        if body_only:
            assert 'No attachment' in registered.text and '&lt;script&gt;' in registered.text
            assert 'Drive filing is pending' not in registered.text
    finally:
        c.execute("DELETE FROM document_role_grant WHERE created_at='email-queue-http'");c.commit()
        for key,value in old.items():st.set_setting(c,'documents.'+key,value)
        c.close()


def test_body_only_replay_limits_and_no_drive_operations(setup):
    c,path,uid,client=setup;enable(c,uid);user={'id':uid}
    source={**payload(),'attachments':[],'body_text':'Please prepare a response.\nThank you.'}
    result=signed(client,source);assert result.status_code==201,result.text
    iid=result.json()['intake_id']
    assert not c.execute('SELECT 1 FROM document_sequence').fetchone()
    assert signed(client,source).json()['duplicate']
    assert signed(client,{**source,'body_text':'Changed'}).status_code==409
    item=intake.claim(c,user,iid,intake.get(c,user,iid)['revision'])
    drive=Drive()
    doc=intake.register(c,user,iid,item['revision'],{**item['draft'],'confirmed':'yes'},adapter=drive)
    assert doc['instruction_state']=='pending' and drive.calls==[]
    intake.file_pending(c,drive);assert drive.calls==[]
    assert intake.get(c,user,iid)['email']['body_text']==source['body_text']
    assert signed(client,source).json()['duplicate']
    for body in ['', 'x'*16001, 'a\x00b']:
        assert signed(client,{**source,'message_id':'19cc','body_text':body}).status_code==400
