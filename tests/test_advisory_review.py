"""Synthetic Chief/Director workflow; no real notification delivery."""
import uuid
import pytest
import advisory_review as review
import advisory_workflow as aw
import documents as d
import documents_permissions as p
import storage as st
import work_discussion
from tests.test_advisory_workflow import drafts, create, options, FIELDS

@pytest.fixture
def cycle(drafts):
    c,users,unit,other,ev,path=drafts
    bureau=st.add_org_unit(c,'Test bureau','bureau','TEST')
    for user,seat,title in [(users[2],unit,'Division Chief'),(users[1],bureau,'Director')]:
        rp=st.add_rp(c,title,is_internal=True,org_unit_id=seat)
        c.execute('UPDATE resource_person SET position=?,designation=? WHERE id=?',(title,title,rp))
        c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,user['id']))
    c.commit()
    return drafts,create(drafts)


def act(c,user,record,action,**data):
    return review.mutate(c,user,record['id'],record['revision'],action,
                        {'operation_key':str(uuid.uuid4()),'reason':'Synthetic '+action,**data})


def test_two_stages_idempotency_and_private_history(cycle):
    data,r=cycle;c,u,*_=data
    request={'operation_key':str(uuid.uuid4()),'reason':'Ready for review'}
    submitted=review.mutate(c,u[0],r['id'],r['revision'],'submit',request)
    assert review.mutate(c,u[0],r['id'],r['revision'],'submit',request)['revision']==submitted['revision']
    assert c.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]==1
    with pytest.raises(p.Denied):act(c,u[1],submitted,'approve')
    with pytest.raises(ValueError):act(c,u[2],submitted,'approve')
    endorsed=act(c,u[2],submitted,'endorse')
    assert d.raw(c,r['document_id'])['approved_version'] is None
    with pytest.raises(d.Conflict):act(c,u[2],submitted,'endorse')
    approved=act(c,u[1],endorsed,'approve')
    doc=d.raw(c,r['document_id'])
    assert doc['status']=='approved' and doc['approved_version']==doc['current_version']
    assert c.execute('SELECT COUNT(*) FROM advisory_decision').fetchone()[0]==2
    assert c.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]==3
    assert c.execute('SELECT COUNT(*) FROM document_job').fetchone()[0]==0
    assert review.screen(c,u[0],approved)['status']=='approved'


@pytest.mark.parametrize('stage',['chief','director'])
def test_returns_revisions_and_resubmission_restart_chief(cycle,stage):
    data,r=cycle;c,u,unit,_,ev,_=data
    r=act(c,u[0],r,'submit')
    if stage=='director':r=act(c,u[2],r,'endorse')
    old=r['current_revision'];r=act(c,u[2] if stage=='chief' else u[1],r,'return')
    opts=options(c,ev,unit);opts.update(expected_revision=r['revision'],summary='Address feedback')
    r=aw.save_draft(c,u[0],ev['event_token'],{**FIELDS,'headline':'Revised'},**opts)
    assert r['current_revision']!=old and r['ordinal']==2
    r=act(c,u[0],r,'submit')
    assert d.raw(c,r['document_id'])['reviewer_id']==u[2]['id']
    with pytest.raises(p.Denied):act(c,u[1],r,'approve')
    r=act(c,u[2],r,'endorse');act(c,u[1],r,'approve')
    assert len(aw.history(c,u[0],r['id']))==2


def test_discussion_preserves_stage_and_revision_and_concerns(cycle):
    data,r=cycle;c,u,*_=data
    r=act(c,u[0],r,'submit');r=act(c,u[2],r,'endorse')
    r=act(c,u[1],r,'comment',reason='Please clarify')
    cid=c.execute('SELECT comment_id FROM advisory_comment').fetchone()[0]
    r=act(c,u[0],r,'comment',reason='Clarification',parent_id=cid,revision_id=r['current_revision'])
    assert d.raw(c,r['document_id'])['reviewer_id']==u[1]['id']
    with pytest.raises(p.Denied):act(c,u[0],r,'resolve',comment_id=cid)
    r=act(c,u[1],r,'resolve',comment_id=cid)
    assert review.screen(c,u[0],r)['discussion'][-1]['concern']=='resolved'
    r=act(c,u[1],r,'reopen_concern',comment_id=cid)
    assert review.screen(c,u[0],r)['discussion'][-1]['concern']=='open'
    c.execute('BEGIN IMMEDIATE')
    with pytest.raises(ValueError):work_discussion.post_in_transaction(c,u[0],r['case_id'],'Bypass')
    c.rollback()
    assert c.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]==2


def test_changed_oic_requires_explicit_restart_and_revokes_old_access(cycle):
    data,r=cycle;c,u,unit,*_=data
    r=act(c,u[0],r,'submit')
    uid=st.create_admin_user(c,'replacement','hash','salt','viewer',active=True)
    st.set_section_oic(c,unit,uid);c.commit()
    with pytest.raises(d.Conflict):act(c,u[2],r,'endorse')
    r=act(c,u[0],r,'reroute')
    with pytest.raises(p.Denied):aw.get_visible(c,u[2],r['id'])
    r=act(c,{'id':uid},r,'endorse');act(c,u[1],r,'approve')


def test_self_review_and_disabled_modules_fail_atomically(cycle):
    data,r=cycle;c,u,unit,*_=data
    st.set_section_oic(c,unit,u[0]['id']);c.commit()
    with pytest.raises(ValueError,match='different people'):act(c,u[0],r,'submit')
    assert not c.execute('SELECT 1 FROM advisory_review_packet').fetchone()
    st.clear_section_oic(c,unit);st.set_setting(c,'work.enabled','0');c.commit()
    with pytest.raises(ValueError):act(c,u[0],r,'submit')
    assert not c.execute('SELECT 1 FROM advisory_review_packet').fetchone()


def test_my_desk_guidance_and_notice_failure_do_not_repeat_decisions(cycle,monkeypatch):
    import documents_actions, documents_notify, send_reminders
    from tests.test_documents_guidance import view
    data,r=cycle;c,u,*_=data
    r=act(c,u[0],r,'submit')
    guide=view(c,u[2],d.raw(c,r['document_id']))
    assert guide['owner_id']==u[2]['id'] and guide['action']['href']=='/advisories/'+str(r['id'])
    st.set_setting(c,'documents.sending_enabled','1');c.commit()
    monkeypatch.setattr(st,'email_feature_enabled',lambda *a:True)
    import mailer
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    calls=[]
    def failed(*a,**k):calls.append(a);raise TimeoutError('Synthetic uncertain send')
    monkeypatch.setattr(send_reminders,'_send',failed)
    assert documents_notify.deliver(c,'https://office.test')==0
    assert documents_notify.deliver(c,'https://office.test')==0
    assert len(calls)==1
    assert c.execute('SELECT state FROM document_notice').fetchone()[0]=='unknown'
    assert d.raw(c,r['document_id'])['status']=='in_review'
    r=act(c,u[2],r,'endorse')
    assert c.execute('SELECT COUNT(*) FROM document_review').fetchone()[0]==1


def test_unconfigured_notice_retry_and_unknown_protection(cycle,monkeypatch):
    import documents_notify, mailer, send_reminders
    data,r=cycle;c,u,*_=data
    r=act(c,u[0],r,'submit')
    st.set_setting(c,'documents.sending_enabled','1');c.commit()
    monkeypatch.setattr(st,'email_feature_enabled',lambda *a:True)
    monkeypatch.setattr(mailer,'email_configured',lambda:False)
    documents_notify.deliver(c,'https://office.test')
    nid=c.execute('SELECT id FROM document_notice').fetchone()[0]
    assert c.execute('SELECT state FROM document_notice').fetchone()[0]=='failed'
    r=act(c,u[0],r,'notice_retry',notice_id=nid)
    calls=[]
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    monkeypatch.setattr(send_reminders,'_send',lambda *a,**k:calls.append(a) or {'sent':True})
    assert documents_notify.deliver(c,'https://office.test')==1
    assert documents_notify.deliver(c,'https://office.test')==0 and len(calls)==1
    with pytest.raises(ValueError):act(c,u[0],r,'notice_retry',notice_id=nid)
    c.execute("UPDATE document_notice SET state='unknown' WHERE id=?",(nid,));c.commit()
    with pytest.raises(ValueError):documents_notify.retry(c,u[2],r['document_id'],nid,'Uncertain')


def test_uncertain_notice_requires_recorded_evidence_before_retry(cycle):
    import documents_notify
    data,r=cycle;c,u,*_=data;r=act(c,u[0],r,'submit')
    nid=c.execute('SELECT id FROM document_notice').fetchone()[0]
    c.execute("UPDATE document_notice SET state='unknown' WHERE id=?",(nid,));c.commit()
    with pytest.raises(ValueError):act(c,u[0],r,'notice_retry',notice_id=nid)
    r=act(c,u[0],r,'notice_no_effect',notice_id=nid,reason='Synthetic provider confirms the request was rejected before sending')
    r=act(c,u[0],r,'notice_retry',notice_id=nid)
    assert c.execute('SELECT state FROM document_notice WHERE id=?',(nid,)).fetchone()[0]=='pending'
    assert c.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM advisory_review_packet').fetchone()[0]==1
