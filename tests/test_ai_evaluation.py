"""Versioned A22 questions against real auth/HTTP/storage and simulated provider HTTP.

Expected values are reviewed literals in cases-v1.json, never calculated by the
AI renderer or derived from the provider's reply. No provider network is allowed.
"""
from datetime import date
import json
import socket
import sqlite3

import httpx
import pytest

import ai_core as ai
import ai_facts
import app as application
from scripts.ai_evaluation import load_suite, REFERENCE
import storage as st
import tzutil

SUITE = load_suite()
SCENARIOS = {'baseline', 'deactivate-route', 'deactivate-select', 'demote-select', 'logout-select',
             'people-select', 'edit-select', 'archive-select', 'date-select', 'router-action',
             'timeout-select', 'http503-select', 'http429-select', 'malformed-select', 'budget', 'disabled'}


@pytest.fixture
def evaluation_world(db_path, viewer, admin, monkeypatch):
    reference = json.loads(REFERENCE.read_text())
    assert tzutil.now_local().isoformat() == reference['reference_clock'] == SUITE['reference_clock']
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # This is a private copy of the synthetic fixture database, never app data.
    for table in ('ai_interaction', 'ai_budget', 'learned_rule', 'answer', 'response', 'form_instance'):
        conn.execute('DELETE FROM ' + table)
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    for key, value in {'ai_mode': 'answers', 'ai_answer_engine': 'maximize',
                       'ai_feature_nl_answer_grounded': '1', 'ai_answer_people': '0',
                       'ai_rules_enabled': '0', 'ai_fallback_enabled': '0', 'ai_log_prompts': '0'}.items():
        st.set_setting(conn, key, value)
    conn.execute("INSERT INTO resource_person(id,name,is_internal) VALUES(9001,'EVAL-PRIVATE-PERSON',0)")
    for form in reference['forms']:
        fid, survey = form['id'], form['survey_type']
        conn.execute('''INSERT INTO form_instance(id,survey_type,form,qr_token,event_date,topic,rp_id,archived)
            VALUES(?,?,?,?,?,?,?,?)''', (fid, survey, f'F{survey}', f'eval-{fid}', form['event_date'],
                                       form['topic'], form.get('rp_id'), int(form.get('archived', False))))
        for response in form['responses']:
            rid = conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES(?,?,?)',
                               (fid, response['submitted_at'], 'EVAL-PRIVATE-REMARK')).lastrowid
            for item, value, na in response['ratings']:
                conn.execute('INSERT INTO answer(response_id,item_id,value,is_na) VALUES(?,?,?,?)', (rid, item, value, na))
    conn.commit()
    for actor in ('viewer', 'admin'):
        uid = st.get_admin_user(conn, actor + '@test.local')['id']
        st.cal_create(conn, 'EVAL-ONLY-' + actor.upper(), '2026-10-20', audience='people',
                      people=[(uid, 'attending')], by='evaluation@test.local')
    monkeypatch.setenv('CSS_GEMINI_API_KEY', 'offline-evaluation-key')
    monkeypatch.setenv('CSS_GEMINI_MODEL', 'gemini-evaluation-fixture')
    monkeypatch.setenv('CSS_GROQ_API_KEY', '')
    ai.reset_cooldown()
    network = []
    def deny(*args, **kwargs):
        network.append(True)
        raise AssertionError('An offline evaluation attempted real network I/O')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    yield conn, {'viewer': viewer, 'admin': admin}, monkeypatch
    conn.close()
    ai.reset_cooldown()
    assert not network, 'Offline evaluation attempted network I/O even if the route caught the error'


@pytest.mark.parametrize('case', [
    pytest.param(case, id=case['id'], marks=pytest.mark.ai_evaluation(case['id'])) for case in SUITE['cases'] if case.get('surface', 'answers') == 'answers'
])
def test_existing_ai_scenario(case, evaluation_world):
    conn, clients, monkeypatch = evaluation_world
    assert case['scenario'] in SCENARIOS, 'Add an explicit implementation for this scenario'
    actor, scenario = case.get('actor', 'viewer'), case['scenario']
    if scenario == 'people-select':
        st.set_setting(conn, 'ai_answer_people', '1')
    elif scenario == 'budget':
        st.set_setting(conn, 'ai_cap_nl_answer_grounded', '0')
    elif scenario == 'disabled':
        st.set_setting(conn, 'ai_feature_nl_answer_grounded', '0')
    calls, mutated = [], set()

    def mutate(stage):
        if not scenario.endswith('-' + stage) or scenario in mutated:
            return
        mutated.add(scenario)
        if scenario.startswith('deactivate-'):
            conn.execute('UPDATE admin_user SET active=0 WHERE username=?', (actor + '@test.local',))
        elif scenario.startswith('demote-'):
            conn.execute("UPDATE admin_user SET role='viewer' WHERE username=?", (actor + '@test.local',))
        elif scenario.startswith('logout-'):
            conn.execute('DELETE FROM login_session')
        elif scenario.startswith('people-'):
            st.set_setting(conn, 'ai_answer_people', '0')
        elif scenario.startswith('edit-'):
            conn.execute("INSERT INTO response(form_instance_id,submitted_at) VALUES(1002,'2026-10-20T10:00')")
        elif scenario.startswith('archive-'):
            conn.execute('UPDATE form_instance SET archived=1 WHERE id=1002')
        elif scenario.startswith('date-'):
            monkeypatch.setattr(application, '_today_local', lambda: date(2026, 10, 21))
        conn.commit()

    def provider_http(url, *, headers, timeout, **kwargs):
        # The real provider adapter builds/parses these requests; intercept only
        # the HTTP boundary, so retries, JSON failures and timeouts are exercised.
        payload = kwargs['json']
        assert url == ai.GEMINI_API_BASE + '/models/gemini-evaluation-fixture:generateContent'
        assert headers['x-goog-api-key'] == 'offline-evaluation-key'
        assert timeout.read <= 8 and timeout.connect <= 3
        assert payload['generationConfig']['maxOutputTokens'] <= 1280
        system = payload['systemInstruction']['parts'][0]['text']
        prompt = payload['contents'][0]['parts'][-1]['text']
        stage = 'select' if system == ai_facts.SYSTEM else 'route'
        calls.append((stage, prompt))
        # User calendar contents, comments and unshared professional names must
        # never leave the server in a provider request.
        for private in ('EVAL-ONLY-VIEWER', 'EVAL-ONLY-ADMIN', 'EVAL-PRIVATE-REMARK'):
            assert private not in prompt
        if scenario != 'people-select':
            assert 'EVAL-PRIVATE-PERSON' not in prompt
        if stage == 'select':
            offered = json.loads(prompt)
            assert offered['question'] == case['question']
            assert all(set(row) == {'id', 'description', 'group'} for row in offered['catalogue'])
            assert not any('value' in row or 'denominator' in row for row in offered['catalogue'])
        mutate(stage)
        if stage == 'select' and scenario == 'timeout-select':
            raise httpx.ReadTimeout('offline timeout fixture')
        if stage == 'select' and scenario in ('http503-select', 'http429-select'):
            return httpx.Response(503 if scenario == 'http503-select' else 429, text='offline provider failure')
        if stage == 'select' and scenario == 'malformed-select':
            return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': '{invalid-json'}]}}]})
        result = (case['plan'] if stage == 'select' else
                  {'kind': 'action', 'action_key': 'archive_activity', 'args': {'fid': 1002}, 'confidence': .99}
                  if scenario == 'router-action' else
                  {'kind': 'answer', 'answer_slot': case.get('slot', 'data_question'), 'confidence': .9})
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': json.dumps(result)}]}}],
                                         'usageMetadata': {'promptTokenCount': 5, 'candidatesTokenCount': 5}})

    monkeypatch.setattr(httpx, 'post', provider_http)
    response = clients[actor].post('/api/ai/route', data={'q': case['question']})
    assert response.status_code == 200
    body, expected = response.json(), case['expect']
    assert len(calls) == expected['calls']
    outcomes = [row[0] for row in conn.execute("SELECT outcome FROM ai_interaction WHERE feature='nl_answer_grounded' ORDER BY id")]
    assert outcomes == expected['outcomes']
    assert body['kind'] == expected['kind']
    if expected['kind'] == 'fallback':
        assert body == {'kind': 'fallback'}
    else:
        assert all(fragment in body['text'] for fragment in expected['text_contains'])
        if expected['sources'] is not None:
            assert body['served_by'] == 'verified_facts' and body['contract_version'] == 1
            assert body['sources'] == [dict(source, as_of='2026-10-20') for source in expected['sources']]
            assert body['text'].endswith(' As of 2026-10-20.')
        if case.get('slot') == 'calendar_today':
            other = 'admin' if actor == 'viewer' else 'viewer'
            assert 'EVAL-ONLY-' + other.upper() not in body['text']
    # The injected action is never executed; only the explicit test mutation
    # may change the source. No test grants the model approval/write authority.
    if scenario != 'archive-select':
        assert conn.execute('SELECT archived FROM form_instance WHERE id=1002').fetchone()[0] == 0
