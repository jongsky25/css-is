"""A22 report draft cases: real routes, sources, identities and provider HTTP.

Reviewed source arithmetic and expected facts live in reference-v1.json.
Only the HTTP boundary is simulated. No production data or provider is used.
"""
import copy
from datetime import date
import io
import json
import socket
import sqlite3
from urllib.parse import unquote

import httpx
import pytest
from docx import Document

import ai_core as ai
import ai_report_drafts as drafts
from scripts.ai_evaluation import load_suite, REFERENCE
import storage as st

SUITE = load_suite()
CASES = [c for c in SUITE['cases'] if c.get('surface') == 'report_draft']
SCENARIOS = {'baseline', 'missing', 'no-data', 'viewer', 'deactivate', 'demote', 'logout', 'edit',
             'new-response', 'archive', 'move-date', 'day', 'human-edit', 'timeout', 'http503',
             'http429', 'malformed', 'budget', 'disabled', 'disable-during', 'off-during',
             'audit-failure', 'save-failure'}


@pytest.fixture
def report_world(app_mod, manager, viewer, monkeypatch):
    reference = json.loads(REFERENCE.read_text())['report_drafts']
    conn = sqlite3.connect(app_mod.DB, check_same_thread=False)
    for table in ('ai_interaction', 'ai_budget', 'report_draft', 'answer', 'response', 'form_instance'):
        conn.execute('DELETE FROM ' + table)
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    for key, value in {'ai_mode': 'router', 'ai_fallback_enabled': '0', 'ai_log_prompts': 'masked'}.items():
        st.set_setting(conn, key, value)
    for form in reference['forms']:
        fid = form['id']
        conn.execute('''INSERT INTO form_instance(id,survey_type,form,qr_token,event_date,topic,venue)
                        VALUES(?,?,?,?,?,?,?)''',
                     (fid, form['survey_type'], f"F{form['survey_type']}", f'report-eval-{fid}',
                      form['event_date'], form['topic'], f'EVAL-DRAFT-PRIVATE-VENUE-{fid}'))
        for response in form['responses']:
            rid = conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES(?,?,?)',
                               (fid, response['submitted_at'], 'EVAL-DRAFT-PRIVATE-COMMENT')).lastrowid
            for item, value, na in response['ratings']:
                conn.execute('INSERT INTO answer(response_id,item_id,value,is_na) VALUES(?,?,?,?)',
                             (rid, item, value, na))
    conn.commit()
    app_mod.invalidate_atoms()
    monkeypatch.setenv('CSS_GEMINI_API_KEY', 'offline-report-evaluation-key')
    monkeypatch.setenv('CSS_GEMINI_MODEL', 'gemini-report-evaluation')
    monkeypatch.setenv('CSS_GROQ_API_KEY', '')
    ai.reset_cooldown()
    network = []
    def deny(*args, **kwargs):
        network.append(True)
        raise AssertionError('Offline report evaluation attempted network I/O')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    yield conn, app_mod, reference, manager, viewer, monkeypatch
    conn.close()
    ai.reset_cooldown()
    assert not network, 'Network I/O was attempted, including errors swallowed by a route'


@pytest.mark.parametrize('case', [pytest.param(c, id=c['id'], marks=pytest.mark.ai_evaluation(c['id'])) for c in CASES])
def test_report_draft_scenario(case, report_world):
    conn, app_mod, reference, manager, viewer, monkeypatch = report_world
    kind, scenario = case['report'], case['scenario']
    assert scenario in SCENARIOS
    fid = 2001 if kind == 'mrr' else 2002
    scope = 'activity_mrr' if kind == 'mrr' else 'csm_closing'
    key = '2001' if kind == 'mrr' else reference['period']
    fields = ('analysis', 'action', 'next_steps', 'resources') if kind == 'mrr' else ('action_plan', 'continuous_improvement')
    for field in fields:
        st.set_report_draft(conn, scope, key, field, 'Existing reviewed ' + field, actor='human')
    previous = st.get_report_drafts(conn, scope, key)
    if scenario == 'missing':
        conn.execute('UPDATE answer SET value=NULL WHERE response_id IN (SELECT id FROM response WHERE form_instance_id=?)', (fid,))
    elif scenario == 'no-data':
        conn.execute("UPDATE response SET archived_at='2026-10-20T05:00:00' WHERE form_instance_id=?", (fid,))
    elif scenario == 'budget':
        st.set_setting(conn, 'ai_cap_report_draft', '0')
    elif scenario == 'disabled':
        st.set_setting(conn, 'ai_feature_report_draft', '0')
    conn.commit()
    calls, mutated = [], []
    expected_facts = copy.deepcopy(reference['expected_facts'][kind])
    if scenario == 'missing' and kind == 'csm':
        expected_facts['overall'] = None
        for dim in expected_facts['dimensions']:
            dim['score'] = None

    def mutate():
        if mutated:
            return
        mutated.append(True)
        if scenario == 'deactivate':
            conn.execute("UPDATE admin_user SET active=0 WHERE username='manager@test.local'")
        elif scenario == 'demote':
            conn.execute("UPDATE admin_user SET role='viewer' WHERE username='manager@test.local'")
        elif scenario == 'logout':
            conn.execute('DELETE FROM login_session')
        elif scenario == 'edit':
            conn.execute('UPDATE answer SET value=1 WHERE item_id=? AND response_id IN '
                         '(SELECT id FROM response WHERE form_instance_id=?)', ('B5' if kind == 'mrr' else 'SQD1', fid))
        elif scenario == 'new-response':
            conn.execute("INSERT INTO response(form_instance_id,submitted_at) VALUES(?,'2026-10-20T06:00:00')", (fid,))
        elif scenario == 'archive':
            conn.execute('UPDATE form_instance SET archived=1 WHERE id=?', (fid,))
        elif scenario == 'move-date':
            if kind == 'mrr':
                conn.execute("UPDATE form_instance SET event_date='2026-10-09' WHERE id=?", (fid,))
            else:
                conn.execute("UPDATE response SET submitted_at='2025-10-09T09:00:00' WHERE form_instance_id=?", (fid,))
        elif scenario == 'day':
            monkeypatch.setattr(app_mod, '_today_local', lambda: date(2026, 10, 21))
        elif scenario == 'human-edit':
            st.set_report_draft(conn, scope, key, fields[0], 'New human correction', actor='manager@test.local')
        elif scenario == 'disable-during':
            st.set_setting(conn, 'ai_feature_report_draft', '0')
        elif scenario == 'off-during':
            st.set_setting(conn, 'ai_mode', 'off')
        conn.commit()

    def provider_http(url, *, headers, timeout, **kwargs):
        assert url == ai.GEMINI_API_BASE + '/models/gemini-report-evaluation:generateContent'
        assert headers['x-goog-api-key'] == 'offline-report-evaluation-key'
        assert timeout.read <= 8 and timeout.connect <= 3
        payload = kwargs['json']
        assert payload['generationConfig']['maxOutputTokens'] <= 96
        assert payload['generationConfig']['responseSchema'] == drafts.schema()
        prompt = payload['contents'][0]['parts'][-1]['text']
        assert json.loads(prompt) == {'contract_version': 1, 'evidence': expected_facts}
        for private in ('EVAL-DRAFT-', 'manager@test.local', 'Existing reviewed', '999999', 'IGNORE RULES'):
            assert private not in prompt
        calls.append(True)
        mutate()
        if scenario == 'timeout':
            raise httpx.ReadTimeout('offline report timeout')
        if scenario in ('http503', 'http429'):
            return httpx.Response(503 if scenario == 'http503' else 429, text='EVAL-DRAFT-PRIVATE-PROVIDER-ERROR')
        text = '{malformed' if scenario == 'malformed' else json.dumps(case['reply'])
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': text}]}}],
                                         'usageMetadata': {'promptTokenCount': 5, 'candidatesTokenCount': 5}})

    monkeypatch.setattr(httpx, 'post', provider_http)
    if scenario == 'audit-failure':
        original = st.audit
        def fail_audit(*args, **kwargs):
            if args[2] in ('ai_mrr_draft', 'ai_csm_draft'):
                raise sqlite3.OperationalError('synthetic audit failure')
            return original(*args, **kwargs)
        monkeypatch.setattr(st, 'audit', fail_audit)
    elif scenario == 'save-failure':
        original = st.set_report_draft
        def fail_save(*args, **kwargs):
            if args[3] == fields[1]:
                raise sqlite3.OperationalError('synthetic field failure')
            return original(*args, **kwargs)
        monkeypatch.setattr(st, 'set_report_draft', fail_save)
    client = viewer if scenario == 'viewer' else manager
    path = '/reports/activities/2001/ai-mrr-draft' if kind == 'mrr' else '/reports/csm-draft'
    if scenario in ('audit-failure', 'save-failure'):
        with pytest.raises(sqlite3.OperationalError):
            client.post(path, data={'period': key}, follow_redirects=False)
    else:
        response = client.post(path, data={'period': key}, follow_redirects=False)
        assert response.status_code == case['expect']['status']
        if response.status_code == 303:
            notice = unquote(response.headers['location'])
            assert ('review and edit' if case['expect']['saved'] else
                    'No ' if scenario in ('missing', 'no-data') else 'nothing was changed') in notice
    assert len(calls) == case['expect']['calls']
    assert [r[0] for r in conn.execute("SELECT outcome FROM ai_interaction WHERE feature='report_draft' ORDER BY id")] == case['expect']['outcomes']
    saved = st.get_report_drafts(conn, scope, key)
    if case['expect']['saved']:
        assert set(saved) == set(fields) and all(row['actor'] == 'ai' for row in saved.values())
        text = ' '.join(row['text'] for row in saved.values())
        # Independent literal facts, not a comparison against render() itself.
        if kind == 'mrr':
            assert '2 respondent(s)' in text and '3.0/4' in text
            assert '“Organizers ready to help” (Responsiveness) at 2.0 of 7' in text
            assert '2026-10-10' in text and 'As of 2026-10-20.' in text
            if case['reply']['style'] == 'detailed':
                assert 'gap is -2.00' in text and '6.0 of 7' in text
        elif scenario == 'missing':
            assert 'overall score is unavailable' in text and 'Responsiveness: N/A' in text
            assert '0%' not in text and 'Gather valid dimension ratings' in text
        else:
            assert '2 respondent(s)' in text and '93.8%' in text and 'Responsiveness (50.0%)' in text
            assert 'quarter:2026-Q4' in text and 'As of 2026-10-20.' in text
        for private in ('EVAL-DRAFT-', '999999', 'IGNORE RULES', 'archive_activity'):
            assert private not in text
    elif scenario == 'human-edit':
        assert saved[fields[0]]['text'] == 'New human correction'
        assert all(saved[field] == previous[field] for field in fields[1:])
    else:
        assert saved == previous
    audits = conn.execute("SELECT action FROM audit_log WHERE action IN ('ai_mrr_draft','ai_csm_draft')").fetchall()
    assert len(audits) == int(case['expect']['saved'])
    logs = conn.execute("SELECT prompt_masked,response_masked,error FROM ai_interaction WHERE feature='report_draft'").fetchall()
    assert all(row[:2] == (None, None) and row[2] in (None, 'report_draft_provider_failure') for row in logs)


def test_mrr_fresh_snapshot_and_rounded_tie_use_the_actual_weakest_dimension(report_world):
    conn, app_mod, _, manager, _, monkeypatch = report_world
    # Warm the stale-while-revalidate report caches, then edit without cache
    # invalidation. Both new means round to 2.0; Assurance really is lower.
    app_mod._event_or_404(conn, 2001)
    for item, value in (('B5', 2.04), ('B6', 2.01)):
        conn.execute('UPDATE answer SET value=? WHERE item_id=? AND response_id IN '
                     '(SELECT id FROM response WHERE form_instance_id=2001)', (value, item))
    conn.commit()
    def provider(url, **kwargs):
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [
            {'text': '{"contract_version":1,"style":"detailed"}'}]}}]})
    monkeypatch.setattr(httpx, 'post', provider)
    response = manager.post('/reports/activities/2001/ai-mrr-draft', follow_redirects=False)
    assert response.status_code == 303
    saved = st.get_report_drafts(conn, 'activity_mrr', '2001')
    assert 'lowest rated dimension is “Knowledgeable organizers” (Assurance) at 2.0 of 7' in saved['analysis']['text']
    assert 'gap is -2.39' in saved['analysis']['text']


def test_csm_export_uses_generated_verified_draft_without_another_provider_call(report_world):
    conn, _, reference, manager, _, monkeypatch = report_world
    calls = []
    def provider(url, **kwargs):
        calls.append(True)
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [
            {'text': '{"contract_version":1,"style":"concise"}'}]}}]})
    monkeypatch.setattr(httpx, 'post', provider)
    response = manager.post('/reports/csm-draft', data={'period': reference['period']}, follow_redirects=False)
    assert response.status_code == 303
    response = manager.get('/reports/export', params={
        'type': 1, 'fmt': 'docx', 'style': 'official', 'period': reference['period']})
    assert response.status_code == 200 and len(calls) == 1
    text = '\n'.join(p.text for p in Document(io.BytesIO(response.content)).paragraphs)
    assert '2 respondent(s)' in text and '93.8%' in text and 'Responsiveness (50.0%)' in text
    assert 'Proposed follow-up: confirm owners and dates' in text
    assert 'EVAL-DRAFT-PRIVATE-' not in text


def test_invalid_csm_draft_period_cannot_silently_expand_to_all_time(report_world):
    conn, _, _, manager, _, monkeypatch = report_world
    calls = []
    def deny(*args, **kwargs):
        calls.append(True)
        raise AssertionError('An invalid period reached the provider')
    monkeypatch.setattr(httpx, 'post', deny)
    response = manager.post('/reports/csm-draft', data={'period': 'quarter:2026-Q9'}, follow_redirects=False)
    assert response.status_code == 400 and not calls
    assert conn.execute('SELECT COUNT(*) FROM report_draft').fetchone()[0] == 0
