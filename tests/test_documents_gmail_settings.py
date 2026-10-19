"""Browser configuration and signed intake acceptance with synthetic accounts/mail."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import documents_email as email
import documents_gmail_settings as settings
import documents_intake as intake
import documents_permissions as p
import storage as st
from test_documents import registry
from test_documents_email import payload, signed

SECRET = 'test-only-secret-with-at-least-32-characters'


def ready(c, user, monkeypatch):
    monkeypatch.setenv('CSS_GMAIL_INTAKE_SECRET', SECRET)
    intake.configure(c, user, {'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
    st.set_setting(c, 'documents.drive_last_sync', '2026-10-19T10:00:00')


def fields(user, **extra):
    return {'mailbox':'Office@Example.Test','actor_id':str(user['id']),'enabled':'yes',**extra}


def test_configuration_enables_review_queue_and_signed_replay(registry, monkeypatch):
    c, users, unit, path = registry
    ready(c, users[1], monkeypatch)
    drive_before = intake.settings(c)
    settings.configure(c, users[1], fields(users[1]))
    assert settings.settings(c)['mailbox'] == 'office@example.test'
    assert intake.settings(c) == drive_before
    assert SECRET not in json.dumps(settings.settings(c))
    app = FastAPI()
    app.include_router(email.make_router(lambda:st.connect(path)))
    with TestClient(app) as client:
        first = signed(client)
        assert first.status_code == 201, first.text
        assert first.json()['state'] == 'queued'
        replay = signed(client)
        assert replay.json()['duplicate'] is True
        assert replay.json()['intake_id'] == first.json()['intake_id']
        body = {**payload(), 'message_id':'abcdef', 'attachments':[], 'body_text':'Test correspondence'}
        assert signed(client, body).json()['state'] == 'queued'
        assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM document_sequence').fetchone()[0] == 0
        settings.configure(c, users[1], {'action':'pause'})
        assert signed(client).status_code == 403
    audit = c.execute("SELECT detail_json FROM document_event WHERE action='gmail_intake_configured'").fetchone()[0]
    assert SECRET not in audit
    assert json.loads(audit)['actor_id'] == users[1]['id']


@pytest.mark.parametrize('failure', ['secret', 'short_secret', 'queue', 'drive_check', 'documents', 'mailbox', 'owner'])
def test_invalid_enable_is_atomic(registry, monkeypatch, failure):
    c, users, unit, path = registry
    ready(c, users[1], monkeypatch)
    form = fields(users[1])
    if failure == 'secret': monkeypatch.delenv('CSS_GMAIL_INTAKE_SECRET')
    if failure == 'short_secret': monkeypatch.setenv('CSS_GMAIL_INTAKE_SECRET', 'short')
    if failure == 'queue': st.set_setting(c, 'documents.gmail_review_queue_enabled', '0')
    if failure == 'drive_check': st.set_setting(c, 'documents.drive_last_sync', '')
    if failure == 'documents': st.set_setting(c, 'documents.enabled', '0')
    if failure == 'mailbox': form['mailbox'] = 'not-an-email'
    if failure == 'owner': form['actor_id'] = str(users[4]['id'])
    before = settings.settings(c)
    with pytest.raises(ValueError): settings.configure(c, users[1], form)
    assert settings.settings(c) == before
    assert c.execute("SELECT COUNT(*) FROM document_event WHERE action='gmail_intake_configured'").fetchone()[0] == 0


def test_permissions_and_owner_revocation(registry, monkeypatch):
    c, users, unit, path = registry
    ready(c, users[1], monkeypatch)
    for user in (users[0], users[4]):
        with pytest.raises(p.Denied): settings.configure(c, user, fields(users[1]))
        with pytest.raises(p.Denied): settings.configure(c, user, {'action':'pause'})
    # A records-only officer cannot configure, and a unit-limited grant cannot own intake.
    c.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'records','now')", (users[0]['id'],))
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'now')", (users[3]['id'],unit))
    c.commit()
    with pytest.raises(p.Denied): settings.configure(c, users[0], fields(users[1]))
    assert {a['id'] for a in settings.records_accounts(c)} == {users[0]['id'],users[1]['id']}
    settings.configure(c, users[1], fields(users[0]))
    c.execute("UPDATE document_role_grant SET revoked_at='now' WHERE user_id=?", (users[0]['id'],))
    c.commit()
    with pytest.raises(ValueError): settings.configure(c, users[1], fields(users[0]))
    with pytest.raises(p.Denied): email.ingest(c, payload())
    monkeypatch.delenv('CSS_GMAIL_INTAKE_SECRET')
    settings.configure(c, users[1], {'action':'pause'})
    assert settings.settings(c)['intake_enabled'] == '0'
    assert settings.settings(c)['actor_id'] == str(users[0]['id'])


def test_inactive_owner_and_disabled_draft(registry, monkeypatch):
    c, users, unit, path = registry
    monkeypatch.delenv('CSS_GMAIL_INTAKE_SECRET', raising=False)
    settings.configure(c, users[1], fields(users[1], enabled=''))
    assert settings.settings(c)['intake_enabled'] == '0'
    c.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'records','now')", (users[0]['id'],))
    c.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[0]['id'],))
    c.commit()
    with pytest.raises(ValueError): settings.configure(c, users[1], fields(users[0], enabled=''))
    assert users[0]['id'] not in [a['id'] for a in settings.records_accounts(c)]


def test_http_settings_csrf_validation_and_pause(app_mod, admin, viewer, monkeypatch):
    from test_documents_routes import token
    c = st.connect(app_mod.DB)
    user = st.get_admin_user(c, 'admin@test.local')
    original = dict(c.execute("SELECT key,value FROM app_setting WHERE key LIKE 'documents.%'"))
    url = '/documents/intake/settings'
    try:
        assert admin.get(url).status_code == 403  # General admin alone is insufficient.
        for role in ('records','workflow_admin'):
            c.execute('INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)', (user['id'],role,'gmail-settings-test'))
        c.commit()
        st.set_setting(c, 'documents.enabled', '1')
        ready(c, user, monkeypatch)
        page = admin.get(url)
        assert page.status_code == 200, page.text
        assert 'Work email / Gmail' in page.text and 'admin@test.local' in page.text
        assert SECRET not in page.text
        assert viewer.get(url).status_code == 403
        form = {**fields(user), 'csrf':token(page)}
        assert admin.post(url+'/gmail', data=fields(user)).status_code == 403
        assert viewer.post(url+'/gmail', data=form).status_code == 403
        invalid = admin.post(url+'/gmail', data={**form,'mailbox':'bad address'})
        assert invalid.status_code == 400
        assert 'bad address' in invalid.text and 'Enter the primary Gmail' in invalid.text
        assert 'action="/documents/intake/settings"' in invalid.text
        assert SECRET not in invalid.text
        saved = admin.post(url+'/gmail', data=form)
        assert saved.status_code == 200, saved.text
        assert 'Gmail settings saved' in saved.text and 'office@example.test' in saved.text
        assert settings.settings(c)['intake_enabled'] == '1'
        # The old Drive form cannot silently disable or replace Gmail configuration.
        gmail_before = settings.settings(c)
        drive = intake.settings(c)
        response = admin.post(url, data={'csrf':form['csrf'],'enabled':'yes','inbox':drive['inbox'],'filed':drive['filed']})
        assert response.status_code == 200
        assert settings.settings(c) == gmail_before
        monkeypatch.delenv('CSS_GMAIL_INTAKE_SECRET')
        paused = admin.post(url+'/gmail', data={'csrf':form['csrf'],'action':'pause'})
        assert paused.status_code == 200, paused.text
        assert settings.settings(c)['intake_enabled'] == '0'
    finally:
        c.execute("DELETE FROM document_role_grant WHERE created_at='gmail-settings-test'")
        c.execute("DELETE FROM app_setting WHERE key LIKE 'documents.%'")
        c.executemany('INSERT INTO app_setting(key,value) VALUES (?,?)', original.items())
        c.commit()
        c.close()
