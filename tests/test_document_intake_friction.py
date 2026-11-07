"""Combined reading/prefill uses current claims, source checks and registration gates."""
import pytest

import documents as docs
import documents_intake as intake
import documents_operations as operations
import documents_permissions as permissions
import storage as st
from test_documents import registry
from test_documents_intake import Drive, seed, fields
from test_documents_understanding import reviewed


class SuggestedDrive(Drive):
    def call(self, action, payload, operation):
        result = super().call(action, payload, operation)
        if action == 'extract':
            result['suggestions'] = {
                'subject': 'Source subject', 'sender': 'Regional Office', 'type': 'Letter',
                'document_date': '2026-10-18', 'due_date': '2026-11-20',
                'need_0_action': 'Unreviewed request', 'focus_confirmed': 'yes',
            }
        return result


def test_read_and_fill_preserves_corrections_and_requires_request_review(registry):
    conn, users, _, _ = registry
    seed(registry)
    item = intake.claim(conn, users[1], 1, 1)
    item = intake.save(conn, users[1], 1, item['revision'], {
        **reviewed(), 'subject': 'Corrected title', 'received_at': '2026-10-18T09:00',
    })
    item = intake.extract(conn, users[1], 1, item['revision'], SuggestedDrive(), fill_empty=True)
    assert item['draft']['subject'] == 'Corrected title'
    assert item['draft']['sender'] == 'Regional Office'
    assert item['draft']['type'] == 'Letter'
    assert item['draft']['direction'] == 'IN'
    assert item['draft']['received_at'] == '2026-10-18T09:00'
    assert item['draft']['need_0_action'] == reviewed()['need_0_action']
    assert item['draft']['need_0_confirmed'] == ''
    assert item['draft']['focus_confirmed'] == ''
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM document_sequence').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM document_assignment').fetchone()[0] == 0


def test_cached_read_fills_without_another_provider_call_and_reread_preserves_edits(registry):
    conn, users, _, _ = registry
    seed(registry)
    item = intake.claim(conn, users[1], 1, 1)
    drive = SuggestedDrive()
    item = intake.extract(conn, users[1], 1, item['revision'], drive)
    item = intake.extract(conn, users[1], 1, item['revision'], drive, fill_empty=True)
    assert len(drive.calls) == 1
    assert item['draft']['subject'] == 'Source subject'
    item = intake.save(conn, users[1], 1, item['revision'], {**item['draft'], 'subject': 'My correction'})
    item = intake.extract(conn, users[1], 1, item['revision'], drive, force=True, fill_empty=True)
    assert len(drive.calls) == 2
    assert item['draft']['subject'] == 'My correction'


@pytest.mark.parametrize('change', ['source', 'revision', 'revoke', 'expired', 'folder', 'disabled', 'wrong_source'])
def test_read_and_fill_rechecks_state_after_provider(registry, change):
    conn, users, _, _ = registry
    files = seed(registry)
    item = intake.claim(conn, users[1], 1, 1)
    item = intake.save(conn, users[1], 1, item['revision'], {'subject': 'Preserve me'})

    class ChangingDrive(SuggestedDrive):
        def call(self, action, payload, operation):
            result = super().call(action, payload, operation)
            if change == 'source':
                files[0].update(content_key='changed', fingerprint='changed-version')
                intake.discover(conn, intake.settings(conn), {'inbox': 'inbox_folder_123', 'files': files})
            elif change == 'revision':
                intake.save(conn, users[1], 1, item['revision'], {'subject': 'Concurrent correction'})
            elif change == 'revoke':
                conn.execute("UPDATE document_role_grant SET revoked_at='2026-10-20' WHERE user_id=? AND role='records'", (users[1]['id'],))
            elif change == 'expired':
                conn.execute("UPDATE document_intake SET claim_until='2020-01-01' WHERE id=1")
            elif change == 'folder':
                st.set_setting(conn, 'documents.drive_inbox', 'different_folder_123')
            elif change == 'disabled':
                st.set_setting(conn, 'documents.enabled', '0')
            elif change == 'wrong_source':
                result['content_key'] = 'wrong'
            conn.commit()
            return result

    with pytest.raises((ValueError, permissions.Denied)):
        intake.extract(conn, users[1], 1, item['revision'], ChangingDrive(), fill_empty=True)
    import json
    row = conn.execute('SELECT draft_json,suggestions_json FROM document_intake WHERE id=1').fetchone()
    assert json.loads(row[0])['subject'] == ('Concurrent correction' if change == 'revision' else 'Preserve me')
    assert not json.loads(row[0]).get('sender')
    assert not json.loads(row[1])
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0


@pytest.fixture
def intake_http(app_mod, admin, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'admin@test.local')
    for role in ('records', 'workflow_admin'):
        conn.execute('INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)', (user['id'], role, 'friction-test'))
    conn.commit()
    st.set_setting(conn, 'documents.enabled', '1')
    intake.configure(conn, user, {'enabled': 'yes', 'inbox': 'inbox_folder_123', 'filed': 'filed_folder_123'})
    files = [{'id': f'friction_scan_{i:06}', 'name': f'Letter {i}.pdf', 'mime_type': 'application/pdf',
              'fingerprint': f'v{i}', 'content_key': f'hash{i}', 'size': 100} for i in (1, 2)]
    intake.discover(conn, intake.settings(conn), {'inbox': 'inbox_folder_123', 'files': files})
    drive = SuggestedDrive()
    monkeypatch.setattr(operations, 'get_adapter', lambda: drive)
    yield conn, user, drive
    conn.close()


def test_inbox_review_and_combined_read_route_guards(intake_http, admin, viewer):
    from test_documents_routes import token
    conn, user, drive = intake_http
    page = admin.get('/documents/intake')
    csrf = token(page)
    assert 'value="claim">Review</button>' in page.text
    assert viewer.get('/documents/intake').status_code == 403
    url = '/documents/intake/1'
    assert admin.post(url, data={'action': 'read_fill', 'revision': 1}).status_code == 403
    # Merely opening a record neither claims it nor contacts Drive.
    assert admin.get(url).status_code == 200
    assert intake.get(conn, user, 1)['claimed_by'] is None and not drive.calls
    assert admin.post(url, data={'csrf': csrf, 'action': 'claim', 'revision': 1}).status_code == 200
    item = intake.get(conn, user, 1)
    payload = {'csrf': csrf, 'action': 'read_fill', 'revision': item['revision'], 'subject': 'Typed title'}
    response = admin.post(url, data=payload)
    assert response.status_code == 200
    assert 'Typed title' in response.text and 'Regional Office' in response.text
    assert len(drive.calls) == 1
    assert admin.post(url, data=payload).status_code == 409
    assert len(drive.calls) == 1
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0


def test_failed_read_retains_saved_input_for_manual_registration(intake_http, admin, monkeypatch):
    from test_documents_routes import token
    conn, user, _ = intake_http
    url = '/documents/intake/1'
    csrf = token(admin.get(url))
    item = intake.claim(conn, user, 1, 1)
    class FailedDrive:
        def call(self, *args):
            raise TimeoutError('provider unavailable')
    monkeypatch.setattr(operations, 'get_adapter', lambda: FailedDrive())
    response = admin.post(url, data={**fields(), 'csrf': csrf, 'action': 'read_fill', 'revision': item['revision']})
    assert response.status_code == 400
    assert 'Your saved review is retained' in response.text
    assert intake.get(conn, user, 1)['draft']['subject'] == fields()['subject']
    assert 'Register document' in response.text


@pytest.mark.parametrize('action', ['read_fill', 'reread_fill'])
def test_combined_reads_obey_external_capacity_before_saving(intake_http, admin, monkeypatch, action):
    import documents_external as external
    from test_documents_routes import token
    conn, user, drive = intake_http
    url = '/documents/intake/1'
    csrf = token(admin.get(url))
    item = intake.claim(conn, user, 1, 1)
    async def busy(*args):
        raise external.Busy()
    monkeypatch.setattr(external, 'run', busy)
    response = admin.post(url, data={**fields(), 'csrf': csrf, 'action': action, 'revision': item['revision']})
    assert response.status_code == 503
    assert response.headers['retry-after'] == '3'
    assert intake.get(conn, user, 1)['revision'] == item['revision']
    assert not drive.calls


def test_unsupported_file_offers_manual_review(intake_http, admin):
    conn, user, drive = intake_http
    conn.execute("UPDATE document_intake SET mime_type='application/msword' WHERE id=1")
    conn.commit()
    page = admin.get('/documents/intake/1')
    assert page.status_code == 200
    assert 'Read and fill empty fields' not in page.text
    assert 'enter its details manually' in page.text
    assert not drive.calls
