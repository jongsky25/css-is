"""Offline A22 checks for the landing assistant's help and navigation paths."""
import json

import httpx
import pytest

import ai_core as ai
import app as application
import rooms
from scripts.ai_evaluation import load_suite
import storage as st
from test_ai_action_evaluation import world  # noqa: F401


CASES = [case for case in load_suite()['cases'] if case.get('surface') == 'help_navigation']


@pytest.mark.parametrize('case', [pytest.param(c, id=c['id'], marks=pytest.mark.ai_evaluation(c['id']))
                                  for c in CASES])
def test_help_navigation_scenario(case, world):
    conn, _, clients, monkeypatch = world
    name = case['scenario']
    assert case['id'] == 'route-' + name
    help_case = name.startswith('help-')
    if name == 'nav-budget': st.set_setting(conn, 'ai_cap_nl_router', '0')
    if name == 'nav-disabled': st.set_setting(conn, 'ai_feature_nl_router', '0')
    conn.commit()
    calls = []

    def fake_post(url, *, headers, timeout, **kwargs):
        assert url == ai.GEMINI_API_BASE + '/models/gemini-action-evaluation:generateContent'
        assert headers['x-goog-api-key'] == 'offline-action-key'
        assert timeout.read <= 8 and timeout.connect <= 3
        payload = kwargs['json']
        assert payload['generationConfig']['responseMimeType'] == 'application/json'
        assert payload['generationConfig']['maxOutputTokens'] <= 256
        prompt = payload['contents'][0]['parts'][-1]['text']
        assert 'Destinations' in prompt and 'User request:' in prompt
        calls.append(True)
        if len(calls) == 1:
            if name in ('nav-logout', 'help-logout'):
                conn.execute('DELETE FROM login_session')
            elif name in ('nav-deactivate', 'help-deactivate'):
                conn.execute("UPDATE admin_user SET active=0 WHERE username='admin@test.local'")
            elif name in ('nav-demote', 'help-demote'):
                conn.execute("UPDATE admin_user SET role='viewer' WHERE username='admin@test.local'")
            elif name == 'nav-router-off-during':
                st.set_setting(conn, 'ai_feature_nl_router', '0')
            elif name == 'nav-mode-off-during':
                st.set_setting(conn, 'ai_mode', 'off')
            elif name == 'help-feature-off-during':
                st.set_setting(conn, 'ai_feature_nl_help', '0')
            elif name == 'help-mode-off-during':
                st.set_setting(conn, 'ai_mode', 'router')
            elif name in ('nav-catalog-changed', 'help-catalog-changed'):
                original = application.ai_route_catalog if name.startswith('nav-') else application.help_catalog_for
                def changed(*args, **kwargs):
                    rows = original(*args, **kwargs)
                    return [{**rows[0], 'label': 'Changed after provider'}, *rows[1:]]
                monkeypatch.setattr(application, 'ai_route_catalog' if name.startswith('nav-') else 'help_catalog_for', changed)
            elif name in ('nav-chief-changed', 'help-chief-changed'):
                monkeypatch.setattr(st, 'user_is_approving_chief', lambda *args: False)
            elif name == 'nav-bureau-changed':
                monkeypatch.setattr(st, 'bureau_access_of', lambda *args: 'changed-access')
            elif name == 'nav-room-changed':
                monkeypatch.setattr(rooms, 'is_room_admin', lambda *args: True)
            conn.commit()
        if name == 'nav-timeout': raise httpx.ReadTimeout('synthetic timeout')
        if name == 'nav-http503': return httpx.Response(503, text='PRIVATE-ROUTE-ERROR')
        reply = ({'kind': 'help', 'help_key': 'directory' if name in ('help-valid', 'help-demote') else 'pulse',
                  'confidence': .9} if help_case else
                 {'kind': 'navigate', 'destination': 'users' if name in ('nav-valid', 'nav-demote') else 'pulse',
                  'confidence': .9, 'reason': 'Open the selected page.'})
        if name in ('nav-restricted', 'help-restricted'):
            reply['destination' if not help_case else 'help_key'] = 'users' if not help_case else 'directory'
        if name in ('nav-list-key', 'help-list-key'):
            reply['destination' if not help_case else 'help_key'] = ['pulse']
        if name in ('nav-unknown-key', 'help-unknown-key'):
            reply['destination' if not help_case else 'help_key'] = 'private-unknown'
        if name in ('nav-low-confidence', 'help-low-confidence'): reply['confidence'] = .2
        if name == 'nav-wrong-kind': reply['kind'] = 'action'
        if name == 'nav-list-reason': reply['reason'] = ['unsafe']
        if name == 'nav-html-reason': reply['reason'] = '<img src=x>'
        if name == 'nav-malformed':
            return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': '{invalid'}]}}]})
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': json.dumps(reply)}]}}],
                                         'usageMetadata': {'promptTokenCount': 5, 'candidatesTokenCount': 5}})

    monkeypatch.setattr(httpx, 'post', fake_post)
    actor = clients['viewer' if name in ('nav-restricted', 'help-restricted') else 'admin']
    response = actor.post('/api/ai/route', data={'q': 'Find the appropriate page or guide'})
    assert response.status_code == 200
    body = response.json()
    assert body['kind'] == case['expect']['kind']
    assert len(calls) == case['expect']['calls']
    if body['kind'] == 'navigate':
        assert body['url'].startswith('/') and body['url'] == ('/admin/users' if name == 'nav-valid' else '/dashboard')
        assert body['reason'] == ('' if name in ('nav-list-reason', 'nav-html-reason') else 'Open the selected page.')
    elif body['kind'] == 'help':
        assert body['url'].startswith('/') and body['url'].endswith('tour=1')
        assert body['text'] and body['label']
    else:
        assert body == {'kind': 'fallback'}
    rows = conn.execute('SELECT outcome,feature,destination,prompt_masked,response_masked,error FROM ai_interaction ORDER BY id').fetchall()
    assert [row[0] for row in rows] == case['expect']['outcomes']
    if body['kind'] == 'help': assert rows[-1][1] == 'nl_help'
    if body['kind'] == 'navigate': assert rows[-1][2] == body['destination']
    assert 'PRIVATE-ROUTE-ERROR' not in json.dumps([tuple(row) for row in rows])
