"""Shared UI calendar service keeps atomicity, active actors and active participants."""
import pytest

import calendar_actions as service
from documents_storage import rows,transaction
import storage as st
from tests.test_work import workspace
from tests.test_telegram_actions import FORM


@pytest.mark.parametrize('role',['viewer','encoder','section_manager','admin'])
def test_all_current_ui_roles_can_create_with_atomic_audit_and_outbox(workspace,role,monkeypatch):
    c,users,_,_=workspace
    c.execute('UPDATE admin_user SET role=? WHERE id=?',(role,users[0]['id']));c.commit()
    fields,people,tags=service.prepare(c,users[0],{**FORM,'title':'  Synthetic meeting  ','people':[str(users[1]['id'])]})
    assert fields['title']=='Synthetic meeting'
    with transaction(c):
        eid=service.create_in_transaction(c,users[0],fields,people,tags)
        assert c.in_transaction
        assert rows(c,"SELECT * FROM audit_log WHERE action='calendar_create' AND target_id=?",(eid,))
        assert rows(c,'SELECT * FROM calendar_outbox WHERE entry_id=?',(eid,))
    assert st.cal_get(c,eid)['created_by']==users[0]['username']


def test_caller_transaction_rolls_back_entry_revision_audit_and_email(workspace):
    c,users,_,_=workspace
    fields,people,tags=service.prepare(c,users[0],{**FORM,'people':[str(users[1]['id'])]})
    with pytest.raises(RuntimeError):service.create_in_transaction(c,users[0],fields,people,tags)
    mark=c.execute('SELECT count(*) FROM audit_log').fetchone()[0]
    with pytest.raises(RuntimeError):
        with transaction(c):
            service.create_in_transaction(c,users[0],fields,people,tags)
            raise RuntimeError('Synthetic caller rollback')
    for table in ('calendar_entry','calendar_entry_revision','calendar_outbox'):
        assert c.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
    assert c.execute('SELECT count(*) FROM audit_log').fetchone()[0]==mark


@pytest.mark.parametrize('change',['actor','participant','unsupported','unit'])
def test_service_rechecks_authority_and_rejects_storage_bypasses(workspace,change):
    c,users,_,_=workspace
    fields,people,tags=service.prepare(c,users[0],{**FORM,'people':[str(users[1]['id'])]})
    if change in ('actor','participant'):
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0 if change=='actor' else 1]['id'],));c.commit()
    elif change=='unsupported':fields['source']='import'
    else:fields.update(audience='unit',owner_org_id=999999)
    with pytest.raises(ValueError):service.create(c,users[0],fields,people,tags)
    assert not rows(c,'SELECT * FROM calendar_entry')
