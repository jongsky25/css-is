"""Offline A22 provider-routing checks through the signed-in assistant route."""
import json

import httpx
import pytest

import ai_core as ai
from scripts.ai_evaluation import load_suite
import storage as st
from test_ai_action_evaluation import world  # noqa: F401


CASES = [case for case in load_suite()['cases'] if case.get('surface') == 'groq_routing']


@pytest.mark.parametrize('case', [pytest.param(c, id=c['id'], marks=pytest.mark.ai_evaluation(c['id']))
                                  for c in CASES])
def test_groq_routing_scenario(case, world):
    conn, _, clients, monkeypatch = world
    name = case['scenario']
    assert case['id'] == 'groq-' + name
    ai.reset_groq_cooldown()
    monkeypatch.setenv('CSS_GROQ_API_KEY', 'offline-groq-key')
    monkeypatch.setenv('CSS_GROQ_MODEL', 'offline-groq-model')
    st.set_setting(conn, 'ai_mode', 'router')
    st.set_setting(conn, 'ai_fallback_enabled', '1')
    if name in ('gemini-preferred', 'gemini-503', 'gemini-timeout', 'gemini-malformed'):
        pass
    elif name in ('standalone-ok', 'standalone-no-optin', 'standalone-no-key',
                  'standalone-mode-off', 'standalone-feature-off', 'standalone-budget',
                  'standalone-groq-429', 'standalone-groq-503', 'standalone-groq-malformed',
                  'standalone-stale-session'):
        monkeypatch.setenv('CSS_GEMINI_API_KEY', '')
    elif name.startswith('budget-'):
        st.set_setting(conn, 'ai_cap_nl_router', '0')
    if name in ('budget-no-optin', 'standalone-no-optin'):
        st.set_setting(conn, 'ai_fallback_enabled', '0')
    if name in ('budget-no-key', 'standalone-no-key'):
        monkeypatch.setenv('CSS_GROQ_API_KEY', '')
    if name == 'standalone-mode-off': st.set_setting(conn, 'ai_mode', 'off')
    if name == 'standalone-feature-off': st.set_setting(conn, 'ai_feature_nl_router', '0')
    if name == 'standalone-budget': st.set_setting(conn, 'ai_cap_nl_router', '0')
    if name == 'budget-groq-throttled':
        monkeypatch.setattr(ai.rl, 'allow', lambda bucket, key: bucket != 'ai_groq')
    conn.commit()
    calls = []

    def fake_post(url, *, headers, timeout, **kwargs):
        assert timeout.read <= 8 and timeout.connect <= 3
        payload = kwargs['json']
        if url.startswith(ai.GEMINI_API_BASE):
            assert headers['x-goog-api-key'] == 'offline-action-key'
            assert payload['generationConfig']['responseMimeType'] == 'application/json'
            assert payload['generationConfig']['maxOutputTokens'] <= 256
            calls.append('gemini')
            if name in ('gemini-429', 'gemini-and-groq-429'):
                return httpx.Response(429, text='synthetic quota exhausted')
            if name == 'gemini-503': return httpx.Response(503, text='synthetic unavailable')
            if name == 'gemini-timeout': raise httpx.ReadTimeout('synthetic timeout')
            if name == 'gemini-malformed':
                return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': '{bad'}]}}]})
            answer = {'kind': 'navigate', 'destination': 'pulse', 'confidence': .9,
                      'reason': 'Open your dashboard.'}
            return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': json.dumps(answer)}]}}],
                                             'usageMetadata': {'promptTokenCount': 3, 'candidatesTokenCount': 4}})
        assert url == ai.GROQ_API_BASE + '/chat/completions'
        assert headers['Authorization'] == 'Bearer offline-groq-key'
        assert payload['model'] == 'offline-groq-model'
        assert payload['response_format'] == {'type': 'json_object'}
        assert payload['max_tokens'] <= 256
        assert payload['messages'][-1]['role'] == 'user'
        calls.append('groq')
        if name == 'standalone-stale-session':
            conn.execute('DELETE FROM login_session'); conn.commit()
        if name in ('gemini-and-groq-429', 'standalone-groq-429'):
            return httpx.Response(429, text='synthetic Groq quota exhausted')
        if name == 'standalone-groq-503':
            return httpx.Response(503, text='synthetic Groq unavailable')
        if name == 'standalone-groq-malformed':
            return httpx.Response(200, json={'choices': [{'message': {'content': '{bad'}}]})
        answer = {'kind': 'navigate', 'destination': 'pulse', 'confidence': .9,
                  'reason': 'Open your dashboard.'}
        if name == 'budget-groq-unknown-key': answer['destination'] = 'private-unknown'
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(answer)}}],
                                         'usage': {'prompt_tokens': 3, 'completion_tokens': 4}})

    monkeypatch.setattr(httpx, 'post', fake_post)
    response = clients['admin'].post('/api/ai/route', data={'q': 'Find my dashboard'})
    assert response.status_code == 200
    body = response.json()
    assert body['kind'] == case['expect']['kind']
    if body['kind'] == 'navigate':
        assert body['url'] == '/dashboard'
    else:
        assert body == {'kind': 'fallback'}
    assert calls == case['expect']['calls']
    rows = conn.execute('SELECT outcome,provider,error FROM ai_interaction ORDER BY id').fetchall()
    assert [(row[0], row[1]) for row in rows] == [tuple(x) for x in case['expect']['rows']]
    if name == 'gemini-429': assert ai.cooldown_remaining() > 0
    if name == 'gemini-and-groq-429':
        assert ai.cooldown_remaining() > 0 and ai.groq_cooldown_remaining() > 0
        assert 'groq fallback failed' in rows[-1][2]
    if name == 'standalone-groq-429': assert ai.groq_cooldown_remaining() > 0
    assert 'offline-groq-key' not in json.dumps([tuple(row) for row in rows])
    ai.reset_groq_cooldown()


EXCLUSIONS = [case for case in load_suite()['cases'] if case.get('surface') == 'groq_exclusion']


@pytest.mark.parametrize('case', [pytest.param(c, id=c['id'], marks=pytest.mark.ai_evaluation(c['id']))
                                  for c in EXCLUSIONS])
def test_groq_exclusion_scenario(case, world):
    conn, _, clients, monkeypatch = world
    name = case['scenario']
    assert case['id'] == 'groq-' + name
    monkeypatch.setenv('CSS_GROQ_API_KEY', 'offline-groq-key')
    st.set_setting(conn, 'ai_fallback_enabled', '1')
    st.set_setting(conn, 'ai_mode', 'assistant')
    feature = 'harmonize' if name == 'harmonize-budget' else 'travel_scan'
    st.set_setting(conn, 'ai_feature_' + feature, '1')
    if name.endswith('budget'): st.set_setting(conn, 'ai_cap_' + feature, '0')
    if name == 'image-standalone': monkeypatch.setenv('CSS_GEMINI_API_KEY', '')
    conn.commit()
    calls = []
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: calls.append(True))
    with pytest.raises(ai.AIBudgetExceeded if name.endswith('budget') else ai.AIUnavailable):
        ai.ask(conn, {'id': 1, 'role': 'admin'}, feature, 'Read this source',
               images=[('image/png', b'not-a-real-image')] if feature == 'travel_scan' else None)
    assert not calls
    row = conn.execute('SELECT outcome,provider,prompt_masked,response_masked FROM ai_interaction ORDER BY id DESC LIMIT 1').fetchone()
    assert (row[0], row[1]) == tuple(case['expect']['row'])
    assert row[2] is None and row[3] is None
