"""Reviewed FAQ migrations and semantic boundaries; synthetic data only."""
from datetime import date, timedelta
import sqlite3

import pytest

import app as app_mod
import qa_rules
import storage as st
from tests.test_ai_learned_rules import _no_real_network

MARKER = 'learned_rules_review_20261104'


@pytest.fixture
def rules_db(db_path):
    conn = st.connect(db_path)
    st.init_db(conn)
    conn.execute('DELETE FROM learned_rule')
    conn.execute('DELETE FROM app_setting WHERE key=?', (MARKER,))
    conn.commit()
    yield conn
    conn.close()


def repair(conn):
    st.repair_learned_rules_20261104(conn, app_mod._MONTH_RULE_REPAIRS,
                                   app_mod._REVIEWED_RULE_ADDITIONS)


def legacy(conn, index=0, **changes):
    pattern, target, keywords, _, _ = app_mod._MONTH_RULE_REPAIRS[index]
    return st.create_learned_rule(conn, pattern=pattern, target_key=target,
        keywords=keywords, kind='answer', created_by='system',
        **{'source': 'seed', **changes})


def test_repairs_upgrade_only_untouched_seeds_and_do_not_resurrect(rules_db):
    conn = rules_db
    clean = legacy(conn)
    paused = legacy(conn, 1, enabled=False)
    edited = legacy(conn, 2)
    manual = legacy(conn, 3, source='manual')
    conn.execute("UPDATE learned_rule SET updated_at='2099-01-01' WHERE id=?", (edited,))
    conn.execute('UPDATE learned_rule SET hits=12 WHERE id=?', (clean,))
    conn.commit()
    repair(conn)
    assert st.get_learned_rule(conn, clean)['target_key'] == 'responses_month'
    assert st.get_learned_rule(conn, clean)['hits'] == 12
    for identifier in (paused, edited, manual):
        assert st.get_learned_rule(conn, identifier)['target_key'].endswith('_30d')
    assert not st.get_learned_rule(conn, paused)['enabled']
    booked = next(r for r in st.list_learned_rules(conn) if r['pattern'] == 'book conference')
    st.delete_learned_rule(conn, booked['id'])
    snapshot = st.list_learned_rules(conn)
    repair(conn)
    assert st.list_learned_rules(conn) == snapshot


def test_existing_pattern_wins_over_new_seed(rules_db):
    conn = rules_db
    rid = st.create_learned_rule(conn, pattern='my wellness break', kind='navigate',
                                target_key='wellness_apply', source='manual', enabled=False)
    repair(conn)
    matching = [r for r in st.list_learned_rules(conn) if r['pattern'] == 'my wellness break']
    assert len(matching) == 1 and matching[0]['id'] == rid
    assert not matching[0]['enabled'] and matching[0]['target_key'] == 'wellness_apply'


def test_repair_rolls_back_all_changes_on_failure(rules_db):
    conn = rules_db
    clean = legacy(conn)
    conn.execute("CREATE TEMP TRIGGER stop_rule BEFORE INSERT ON learned_rule WHEN NEW.pattern='request ballpen' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='synthetic failure'):
        repair(conn)
    assert st.get_learned_rule(conn, clean)['target_key'] == 'responses_30d'
    assert len(st.list_learned_rules(conn)) == 1
    assert st.get_setting(conn, MARKER) is None
    conn.execute('DROP TRIGGER stop_rule')
    repair(conn)
    assert st.get_setting(conn, MARKER) == '1'


def seeded_rules(conn):
    app_mod._seed_learned_rules(conn)
    # Office defaults can otherwise be missing after another fixture's reset.
    st.set_setting(conn, 'office_rules_seeded', '')
    app_mod._seed_office_rules(conn)
    repair(conn)
    return st.list_learned_rules(conn)


def test_reviewed_phrases_and_negative_intents(rules_db):
    rules = seeded_rules(rules_db)
    expected = {'my wellness break': 'wellness', 'reserve conference room': 'rooms',
                'book conference': 'rooms', 'blhsd awa': 'work_arrangement',
                'request ballpen': 'supplies',
                'how many wellness do i avail this week': 'wellness_left',
                'how many responses this month': 'responses_month',
                'responses last 30 days': 'responses_30d',
                'how do i encode responses': 'encode'}
    for query, target in expected.items():
        assert qa_rules.match(query, rules)['target_key'] == target
    for query in ('what do i have', 'our tasks', 'our room bookings', 'our approvals waiting',
                  'how much wellness have i used this week', 'total responses for 2026',
                  'do not request ballpen', 'cancel my conference room booking',
                  'reserve conference room on december 3 2026'):
        assert qa_rules.match(query, rules) is None, query


def test_conflicting_exact_and_fuzzy_rules_fall_through():
    rules = [{'pattern': 'my tasks', 'kind': 'answer', 'target_key': t}
             for t in ('todo_summary', 'approvals_waiting')]
    assert qa_rules.match('my tasks', rules) is None
    rules = [{'pattern': phrase, 'kind': 'navigate', 'target_key': target}
             for phrase, target in [('open calendar today', 'calendar'), ('open calendar tomorrow', 'rooms')]]
    assert qa_rules.match('open calendar', rules) is None
    rules[1]['target_key'] = 'calendar'
    assert qa_rules.match('open calendar', rules)['target_key'] == 'calendar'


@pytest.mark.parametrize('today', [date(2026, 11, 4), date(2027, 1, 1), date(2028, 2, 29)])
def test_calendar_month_boundaries_all_four_metrics(rules_db, monkeypatch, today, admin):
    conn = rules_db
    monkeypatch.setattr(app_mod, '_today_local', lambda: today)
    first = today.replace(day=1)
    prefix = 'rule-month-' + today.isoformat()
    for i, (day, value) in enumerate(((first-timedelta(days=1), 7), (first, 7),
                                    (today, 1), (today+timedelta(days=1), 7))):
        person = conn.execute('INSERT INTO resource_person(name,is_internal) VALUES (?,0)', (prefix+str(i),)).lastrowid
        form = conn.execute('INSERT INTO form_instance(survey_type,form,qr_token,event_date,rp_id) VALUES (2,\'F2\',?,?,?)',
                            (prefix+str(i), day.isoformat(), person)).lastrowid
        response = conn.execute('INSERT INTO response(form_instance_id,submitted_at) VALUES (?,?)',
                                (form, day.isoformat()+'T12:00:00')).lastrowid
        conn.execute("INSERT INTO answer(response_id,item_id,value) VALUES (?,'B1',?)", (response,value))
    conn.commit()
    # Isolate only synthetic rows in this month from other fixture history.
    ids = [r[0] for r in conn.execute('SELECT id FROM form_instance WHERE qr_token LIKE ?', (prefix+'%',))]
    conn.execute('DELETE FROM answer WHERE response_id IN (SELECT id FROM response WHERE form_instance_id NOT IN (%s))' % ','.join('?'*len(ids)), ids)
    conn.execute('DELETE FROM response WHERE form_instance_id NOT IN (%s)' % ','.join('?'*len(ids)), ids)
    conn.commit()
    stats = app_mod.home_stats(conn, fresh=True, calendar_month=True)
    assert stats['responses']['month'] == 2
    assert stats['activities']['month'] == 2
    assert stats['people_rated']['month'] == 2
    assert stats['satisfaction']['month'] == 50
    assert 'this calendar month' in app_mod.AI_ANSWER_SLOTS['responses_month']['render'](stats)
    seeded_rules(conn)
    result = admin.post('/api/ai/route', data={'q': 'how many responses this month'}).json()
    assert result['served_by'] == 'rules' and result['kind'] == 'answer'
    assert 'Responses collected: 2 this calendar month' in result['text']


def test_encoding_help_and_navigation_serve_without_model(admin, rules_db):
    seeded_rules(rules_db)
    st.set_setting(rules_db, 'ai_mode', 'off')
    for query, kind, key in [('how do i encode responses','help','encode'),
                             ('my wellness break','navigate','wellness'),
                             ('book conference','navigate','rooms')]:
        result = admin.post('/api/ai/route', data={'q':query}).json()
        assert result['served_by'] == 'rules' and result['kind'] == kind
        if kind == 'navigate':
            assert result['destination'] == key
        else:
            assert result['url'] == '/encode?tour=1'
            assert 'Paper entry records submitted feedback' in result['text']
    body = admin.get('/encode').text
    assert 'data-tour="encode-intro"' in body
    assert 'Find the right activity' in admin.get('/help').text
