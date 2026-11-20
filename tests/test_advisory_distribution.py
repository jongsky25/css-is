"""Frozen audience, independent delivery, no real SMTP/relay/public writes."""
import json
import uuid
import pytest
import advisory_distribution as dist
import advisory_review as review
import advisory_workflow as aw
import documents as d
import documents_operations as ops
import documents_permissions as p
import storage as st
from tests.test_advisory_review import cycle,act
from tests.test_advisory_workflow import drafts,FIELDS,options

@pytest.fixture
def approved(cycle):
    data,r=cycle;c,u,unit,_,ev,_=data
    c.execute('UPDATE admin_user SET active=0 WHERE id NOT IN (?,?,?)',tuple(x['id'] for x in u));c.commit()
    opts=options(c,ev,unit);opts.update(expected_revision=r['revision'],audience='both',external='SHARED@example.invalid, outside@example.invalid',summary='Audience confirmed')
    r=aw.save_draft(c,u[0],ev['event_token'],FIELDS,**opts)
    c.execute("UPDATE resource_person SET email='shared@example.invalid' WHERE id=(SELECT rp_id FROM admin_user WHERE id=?)",(u[2]['id'],))
    c.commit()
    r=act(c,u[0],r,'submit');r=act(c,u[2],r,'endorse');r=act(c,u[1],r,'approve')
    return data,r


def issue(c,u,r):
    preview=dist.preview(c,u,r['id'])
    return act(c,u,r,'issue',confirmation=preview['confirmation'],ack_missing='1')


def deliveries(c):return [r[0] for r in c.execute('SELECT job_id FROM advisory_delivery ORDER BY rowid')]


def test_issue_snapshot_replay_missing_and_attachment_privacy(approved,monkeypatch):
    import mailer,send_reminders
    data,r=approved;c,u,*_=data
    preview=dist.preview(c,u[0],r['id'])
    assert preview['recipients']==['outside@example.invalid','shared@example.invalid'] and len(preview['missing'])==2
    with pytest.raises(ValueError):act(c,u[0],r,'issue',confirmation=preview['confirmation'])
    args={'operation_key':str(uuid.uuid4()),'reason':'Issue','confirmation':preview['confirmation'],'ack_missing':'1'}
    old=r
    r=review.mutate(c,u[0],r['id'],r['revision'],'issue',args)
    assert review.mutate(c,u[0],old['id'],old['revision'],'issue',args)['revision']==r['revision']
    assert len(deliveries(c))==2 and d.raw(c,r['document_id'])['status']=='issued'
    frozen=dist.latest(c,r['id']);pdf=aw.artifact(c,u[0],r['id'],frozen['revision_id'],'pdf')
    c.execute("UPDATE resource_person SET email='new@example.invalid'");c.commit()
    assert json.loads(frozen['recipients_json'])==preview['recipients']
    st.set_setting(c,'documents.sending_enabled','1');c.commit()
    monkeypatch.setattr(st,'email_feature_enabled',lambda *a:True);monkeypatch.setattr(mailer,'email_configured',lambda:True)
    sent=[]
    monkeypatch.setattr(send_reminders,'_send',lambda *a,**k:sent.append((a,k)) or {'sent':True})
    for operation in deliveries(c):assert ops.execute(c,operation)['state']=='confirmed'
    assert [call[0][2] for call in sent]==preview['recipients']
    assert all(call[1]['attachments'][0][2]==pdf for call in sent)
    assert all('example.invalid' not in call[0][4] for call in sent)
    assert c.execute('SELECT COUNT(*) FROM document_dispatch_recipient').fetchone()[0]==2
    with pytest.raises(d.Conflict):ops.execute(c,deliveries(c)[0])
    with pytest.raises(ValueError):act(c,u[0],r,'retry_delivery',job_id=deliveries(c)[0])


def test_roster_change_and_unapproved_issuance_rejected(cycle):
    data,r=cycle;c,u,*_=data
    with pytest.raises(ValueError):dist.preview(c,u[0],r['id'])
    r=act(c,u[0],r,'submit');r=act(c,u[2],r,'endorse');r=act(c,u[1],r,'approve')
    planned=dist.preview(c,u[0],r['id'])
    st.create_admin_user(c,'new@example.invalid','hash','salt','viewer',active=True)
    with pytest.raises(d.Conflict):act(c,u[0],r,'issue',confirmation=planned['confirmation'],ack_missing='1')
    assert not deliveries(c)


def test_uncertain_delivery_requires_evidence_and_failed_retry_is_individual(approved,monkeypatch):
    import mailer,send_reminders
    data,r=approved;c,u,*_=data;r=issue(c,u[0],r)
    st.set_setting(c,'documents.sending_enabled','1');c.commit()
    monkeypatch.setattr(st,'email_feature_enabled',lambda *a:True);monkeypatch.setattr(mailer,'email_configured',lambda:True)
    sent=[];monkeypatch.setattr(send_reminders,'_send',lambda *a,**k:sent.append(a) or {'sent':False})
    operation=deliveries(c)[0]
    assert ops.execute(c,operation)['state']=='unknown'
    assert ops.execute(c,operation,reconcile=True)['state']=='unknown' and len(sent)==1
    with pytest.raises(ValueError):act(c,u[0],r,'retry_delivery',job_id=operation)
    with pytest.raises(d.Conflict):act(c,u[0],r,'cancel_issued')
    r=act(c,u[0],r,'delivery_no_effect',job_id=operation,reason='Synthetic provider confirms no message')
    r=act(c,u[0],r,'retry_delivery',job_id=operation)
    assert len(deliveries(c))==3
    with pytest.raises(ValueError):act(c,u[0],r,'retry_delivery',job_id=operation)
    assert len(sent)==1


def test_public_issue_stays_frozen_during_revision_and_cancellation(approved):
    data,r=approved;c,u,unit,_,ev,_=data;r=issue(c,u[0],r)
    issued=dist.latest(c,r['id']);pdf=aw.artifact(c,u[0],r['id'],issued['revision_id'],'pdf')
    with pytest.raises(ValueError):dist.public_artifact(c,ev['id'],'pdf')
    r=act(c,u[0],r,'publish',issue_id=str(issued['id']))
    assert dist.public_artifact(c,ev['id'],'pdf')==pdf
    r=act(c,u[0],r,'revise_issued')
    opts=options(c,ev,unit);opts.update(expected_revision=r['revision'],summary='Replacement content')
    r=aw.save_draft(c,u[0],ev['event_token'],{**FIELDS,'headline':'Replacement'},**opts)
    assert dist.public_artifact(c,ev['id'],'pdf')==pdf
    r=act(c,u[0],r,'submit');r=act(c,u[2],r,'endorse');r=act(c,u[1],r,'approve')
    # Internal audience needs a deliverable account after the replacement removes externals.
    r=issue(c,u[0],r)
    newer=dist.latest(c,r['id']);assert newer['supersedes_id']==issued['id']
    with pytest.raises(ValueError):dist.public_artifact(c,ev['id'],'pdf')
    with pytest.raises(ValueError):act(c,u[0],r,'publish',issue_id=str(newer['id']))
    r=act(c,u[0],r,'cancel_issued')
    assert not dist.live(c,newer)
    assert aw.artifact(c,u[0],r['id'],issued['revision_id'],'pdf')==pdf


def test_internal_recipient_only_sees_issued_artifact(approved):
    data,r=approved;c,u,*_=data
    uid=st.create_admin_user(c,'reader@example.invalid','hash','salt','viewer',active=True)
    inactive=st.create_admin_user(c,'inactive@example.invalid','hash','salt','viewer',active=False)
    r=issue(c,u[0],r);issued=dist.latest(c,r['id'])
    assert len(dist.issued_for_user(c,{'id':uid}))==1
    assert dist.issued_artifact(c,{'id':uid},issued['id'],'pdf').startswith(b'%PDF-')
    with pytest.raises(p.Denied):aw.get_visible(c,{'id':uid},r['id'])
    assert inactive not in [x['id'] for x in json.loads(issued['roster_json'])]
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(uid,));c.commit()
    with pytest.raises(p.Denied):dist.issued_artifact(c,{'id':uid},issued['id'],'pdf')


def test_explicit_scoped_release_access_and_revocation(approved):
    data,r=approved;c,u,unit,*_=data
    uid=st.create_admin_user(c,'release@example.invalid','hash','salt','viewer',active=True)
    with pytest.raises(p.Denied):act(c,u[0],r,'grant_release',target_id=uid)
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-01-01')",(uid,unit));c.commit()
    r=act(c,u[0],r,'grant_release',target_id=uid)
    assert dist.preview(c,{'id':uid},r['id'])['record']['id']==r['id']
    r=act(c,u[0],r,'revoke_release',target_id=uid)
    with pytest.raises(p.Denied):dist.preview(c,{'id':uid},r['id'])
    r=act(c,u[0],r,'grant_release',target_id=uid)
    r=issue(c,{'id':uid},r)
    assert dist.latest(c,r['id'])['actor_id']==uid


def test_dashboard_counts_filters_pagination_and_denial(approved,monkeypatch):
    import mailer
    data,r=approved;c,u,unit,other,*_=data
    page=aw.list_visible(c,u[0],status='approved',audience='both',unit_id=unit)
    assert page['total']==1 and page['counts']['approved']==1
    assert aw.list_visible(c,u[0],status='chief')['total']==0
    assert aw.list_visible(c,u[0],unit_id=other)['total']==0
    r=issue(c,u[0],r);issued=dist.latest(c,r['id'])
    assert aw.list_visible(c,u[0],status='issued',month=issued['issued_at'][:7])['total']==1
    st.set_setting(c,'documents.sending_enabled','1');c.commit()
    monkeypatch.setattr(st,'email_feature_enabled',lambda *a:True);monkeypatch.setattr(mailer,'email_configured',lambda:False)
    ops.execute(c,deliveries(c)[0])
    page=aw.list_visible(c,u[0],status='delivery_failures',limit=1)
    assert page['total']==1 and page['counts']['delivery_failures']==1 and page['items'][0]['delivery_attention']
    uid=st.create_admin_user(c,'unrelated@example.invalid','hash','salt','admin',active=True)
    assert aw.list_visible(c,{'id':uid},status='delivery_failures')['counts']['all']==0
    r=act(c,u[0],r,'retry_delivery',job_id=deliveries(c)[0])
    assert aw.list_visible(c,u[0],status='delivery_failures')['total']==0


def test_queued_worker_checks_access_and_does_not_send_after_revocation(approved,monkeypatch):
    import mailer,send_reminders
    data,r=approved;c,u,*_=data;r=issue(c,u[0],r)
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));c.commit()
    monkeypatch.setattr(send_reminders,'_send',lambda *a,**k:pytest.fail('Revoked issuer cannot send'))
    with pytest.raises(p.Denied):ops.execute(c,deliveries(c)[0])
    assert c.execute('SELECT COUNT(*) FROM document_dispatch').fetchone()[0]==0


def test_published_activity_summary_uses_only_issued_version(approved):
    import activity_advisory as aa
    data,r=approved;c,u,*_=data
    assert aa.public_summary(c,r['event_id']) is None
    r=issue(c,u[0],r);issued=dist.latest(c,r['id'])
    r=act(c,u[0],r,'publish',issue_id=str(issued['id']))
    assert aa.public_summary(c,r['event_id'])['revision']==issued['revision_id']
    r=act(c,u[0],r,'unpublish',issue_id=str(issued['id']))
    assert aa.public_summary(c,r['event_id']) is None


def test_concurrent_issue_attempts_create_one_snapshot(approved):
    from concurrent.futures import ThreadPoolExecutor
    data,r=approved;c,u,_,_,_,path=data
    preview=dist.preview(c,u[0],r['id'])
    def attempt():
        conn=st.connect(path)
        try:
            act(conn,u[0],r,'issue',confirmation=preview['confirmation'],ack_missing='1')
            return 'issued'
        except d.Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
    assert sorted(results)==['conflict','issued']
    assert c.execute('SELECT COUNT(*) FROM advisory_issue').fetchone()[0]==1
    assert len(deliveries(c))==2
