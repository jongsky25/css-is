"""Versioned, offline A22 checks for participant message suggestions."""
import json
import socket
import sqlite3

import httpx
import pytest

import ai_core as ai
from scripts.ai_evaluation import load_suite, REFERENCE
import storage as st


CASES = [case for case in load_suite()['cases'] if case.get('surface') == 'messages']
FACTS = json.loads(REFERENCE.read_text())['messages']


@pytest.fixture
def world(app_mod, manager, viewer, monkeypatch):
    conn = sqlite3.connect(app_mod.DB, check_same_thread=False)
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    conn.execute('DELETE FROM ai_interaction')
    conn.execute('DELETE FROM ai_budget')
    st.set_setting(conn, 'ai_mode', 'router')
    st.set_setting(conn, 'ai_fallback_enabled', '0')
    st.set_setting(conn, 'ai_log_prompts', 'masked')
    fid = st.create_form_instance(conn, 2, 'F2', FACTS['date'], venue=FACTS['venue'],
                                  topic=FACTS['title'])
    event = st.create_event(conn, FACTS['title'], FACTS['date'], venue=FACTS['venue'],
                            organizer=FACTS['organizer'], form_instance_ids=[fid],
                            created_by='manager@test.local')
    conn.commit()
    monkeypatch.setenv('CSS_GEMINI_API_KEY', 'offline-messages-key')
    monkeypatch.setenv('CSS_GEMINI_MODEL', 'gemini-messages-evaluation')
    monkeypatch.setenv('CSS_GROQ_API_KEY', '')
    monkeypatch.setattr(ai.rl, 'allow', lambda *a, **k: True)
    ai.reset_cooldown()
    network = []
    def deny(*args, **kwargs):
        network.append(True)
        raise AssertionError('Message evaluation attempted real network I/O')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    yield conn, event, manager, viewer, monkeypatch
    conn.close()
    ai.reset_cooldown()
    assert not network


def _reply(name):
    text = FACTS['ending'] if name == 'ending-baseline' else FACTS['welcome']
    if name == 'unsupported-number': text += ' Please arrive at 10:30.'
    elif name == 'no-name': text = text.replace('{name}', 'friend')
    elif name == 'duplicate-name': text += ' See you, {name}.'
    elif name == 'too-long': text += 'x' * 2001
    elif name == 'html': text += ' <script>alert(1)</script>'
    elif name == 'url': text += ' Visit https://malicious.example/path.'
    elif name == 'email': text += ' Send details to private@example.test.'
    elif name == 'phone': text += ' Contact 09171234567.'
    elif name == 'credential-request': text += ' Please share your password.'
    elif name == 'markdown-link': text += ' [Open](javascript:alert(1))'
    elif name == 'control': text += '\x00'
    if name == 'bad-root': return {'unexpected': text}
    if name == 'extra-field': return {'text': text, 'send_to_all': True}
    return {'text': text}


@pytest.mark.parametrize('case', [pytest.param(c, id=c['id'], marks=pytest.mark.ai_evaluation(c['id']))
                                  for c in CASES])
def test_message_scenario(case, world):
    conn, event, manager, viewer, monkeypatch = world
    name = case['scenario']
    assert case['id'] == 'messages-' + name
    if name == 'budget': st.set_setting(conn, 'ai_cap_messages', '0')
    elif name == 'disabled': st.set_setting(conn, 'ai_feature_messages', '0')
    elif name == 'off': st.set_setting(conn, 'ai_mode', 'off')
    elif name == 'phone':
        conn.execute("UPDATE event SET organizer='BLHSD 09171234567' WHERE id=?", (event['id'],))
    conn.commit()
    calls = []

    def fake_post(url, *, headers, timeout, **kwargs):
        assert url == ai.GEMINI_API_BASE + '/models/gemini-messages-evaluation:generateContent'
        assert headers['x-goog-api-key'] == 'offline-messages-key'
        assert timeout.read <= 8 and timeout.connect <= 3
        payload = kwargs['json']
        assert payload['generationConfig']['maxOutputTokens'] <= 300
        prompt = payload['contents'][0]['parts'][-1]['text']
        assert all(value in prompt for value in (FACTS['title'], FACTS['venue'], FACTS['organizer']))
        assert FACTS['private_attendee'] not in prompt
        calls.append(True)
        if name == 'deactivate':
            conn.execute("UPDATE admin_user SET active=0 WHERE username='manager@test.local'")
        elif name == 'demote':
            conn.execute("UPDATE admin_user SET role='viewer' WHERE username='manager@test.local'")
        elif name == 'logout': conn.execute('DELETE FROM login_session')
        elif name == 'disable-during': st.set_setting(conn, 'ai_feature_messages', '0')
        elif name == 'off-during': st.set_setting(conn, 'ai_mode', 'off')
        elif name == 'edit-title':
            conn.execute("UPDATE event SET title='Updated Forum' WHERE id=?", (event['id'],))
        elif name == 'edit-date':
            conn.execute("UPDATE event SET event_date='2099-03-04' WHERE id=?", (event['id'],))
        elif name == 'edit-message':
            conn.execute("UPDATE event SET welcome_message='Human changed this' WHERE id=?", (event['id'],))
        elif name == 'transfer-owner':
            conn.execute("UPDATE event SET created_by='other@test.local' WHERE id=?", (event['id'],))
        conn.commit()
        if name == 'timeout': raise httpx.ReadTimeout('synthetic timeout')
        if name == 'http503': return httpx.Response(503, text='PRIVATE-PROVIDER-ERROR')
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': json.dumps(_reply(name))}]}}],
                                         'usageMetadata': {'promptTokenCount': 4, 'candidatesTokenCount': 4}})

    monkeypatch.setattr(httpx, 'post', fake_post)
    if name == 'audit-fail':
        audit = st.audit
        def fail_audit(*args, **kwargs):
            if args[2] == 'ai_message_draft': raise sqlite3.OperationalError('synthetic audit failure')
            return audit(*args, **kwargs)
        monkeypatch.setattr(st, 'audit', fail_audit)
    client = viewer if name == 'viewer' else manager
    token = 'missing-token' if name == 'missing' else event['event_token']
    path = f'/activities/{token}/messages/ai-draft'
    if name == 'audit-fail':
        with pytest.raises(sqlite3.OperationalError):
            client.post(path, data={'slot': 'welcome', 'tone': 'personal'})
    else:
        response = client.post(path, data={'slot': 'ending' if name == 'ending-baseline' else 'welcome',
                                           'tone': 'personal'})
        if name == 'viewer': assert response.status_code == 403
        elif name == 'missing': assert response.status_code == 404
        else:
            assert response.status_code == 200
            body = response.json()
            assert body['ok'] is case['expect']['ok']
            if body['ok']:
                assert set(body) == {'ok', 'text', 'interaction_id', 'contract_version', 'review_required'}
                assert body['text'] == FACTS['ending' if name == 'ending-baseline' else 'welcome']
                assert body['contract_version'] == 1 and body['review_required'] is True
            else: assert 'notice' in body
    assert len(calls) == case['expect']['calls']
    rows = conn.execute("SELECT outcome,prompt_masked,response_masked,error FROM ai_interaction "
                        "WHERE feature='messages' ORDER BY id").fetchall()
    assert [row[0] for row in rows] == case['expect']['outcomes']
    assert all(row[1:3] == (None, None) and row[3] in (None, 'messages_provider_failure') for row in rows)
    saved = st.get_event(conn, event['event_token'])
    if saved:
        assert saved['welcome_message'] == ('Human changed this' if name == 'edit-message' else None)
        assert saved['ending_message'] is None
    audit_count = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='ai_message_draft' AND target_id=?",
                               (str(event['id']),)).fetchone()[0]
    assert audit_count == int(case['expect']['ok'])
