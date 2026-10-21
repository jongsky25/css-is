"""A13: independent legacy parity, bounded page reads, and current authority.

Synthetic data only; no Drive, Gmail, provider, or production calls.
"""
import json
import re
import html
from urllib.parse import parse_qs, urlsplit

import pytest

import documents as docs
import documents_permissions as permissions
import documents_registry as registry_reads
import storage as st
from tests.test_documents import registry, register, act
from tests.document_registry_reference import legacy_visible, legacy_metrics


QUEUES = ('all', 'IN', 'OUT', 'verification', 'review', 'release', 'mine',
          'mentions', 'unassigned', 'archived', 'gmail', 'gmail_review', 'instruction')


def ids(documents):
    return [doc['id'] for doc in documents]


def grant(conn, user, role, unit=None):
    conn.execute('INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES(?,?,?,?)',
                 (user['id'], role, unit, '2026-10-21'))
    conn.commit()


def seed_many(conn, creator, unit, count, *, subject='Page record', visibility='bureau', verified=True):
    first = conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM document').fetchone()[0]
    conn.executemany('''INSERT INTO document(id,number,direction,subject,type,sender,creator_id,unit_id,
        verification,status,visibility,created_at,updated_at,matches_json)
        VALUES(?,?,'OUT',?,'memo','Office',?,?,?,'registered',?,'2026-10-20T09:00:00',
               '2026-10-20T09:00:00','{}')''',
        [(n, f'REG-{n}', f'{subject} {n:04d}', creator['id'], unit,
          'verified' if verified else 'pending', visibility) for n in range(first, first + count)])
    conn.commit()
    return list(range(first, first + count))


@pytest.fixture
def mixed(registry):
    conn, users, unit, _ = registry
    child = st.add_org_unit(conn, 'Child Section', 'section', 'BLHSD/D1/CHILD')
    other = st.add_org_unit(conn, 'Other Division', 'division', 'BLHSD/D10')
    extra = []
    for name in ('scoped-records', 'scoped-archive', 'division-oic'):
        uid = st.create_admin_user(conn, name + '@example.test', 'hash', 'salt', 'viewer', active=True)
        extra.append(st.get_admin_user_by_id(conn, uid))
    grant(conn, extra[0], 'records', unit)
    grant(conn, extra[1], 'workflow_admin', unit)
    st.set_section_oic(conn, unit, extra[2]['id'], set_by=users[1]['id'])
    records = []
    for n in range(18):
        doc = register(conn, users[0], (unit, child, other, None)[n % 4],
                       'IN' if n % 2 else 'OUT', subject=f'Needle record {n}')
        state = ('registered', 'in_review', 'approved', 'ready_to_release', 'closed', 'cancelled')[n % 6]
        conn.execute('''UPDATE document SET visibility=?,verification=?,status=?,reviewer_id=?,lead_id=?,
            due_date=?,archived_at=?,matches_json=? WHERE id=?''',
            (('preverification', 'bureau', 'restricted')[n % 3],
             'verified' if n % 2 or n == 16 else 'pending', state, users[3]['id'],
             users[3]['id'] if n % 4 == 0 else None,
             ('2026-10-19', '2026-10-22', None)[n % 3],
             '2026-10-21' if n >= 15 else None,
             json.dumps({'unit_ids': [child]} if n in (2, 6) else {}), doc['id']))
        if n % 5 == 0:
            conn.execute('INSERT INTO document_access VALUES (?,?,?)', (doc['id'], users[3]['id'], 'test'))
        if n % 2 == 0:
            conn.execute('''INSERT INTO document_assignment(document_id,user_id,role,action,status,created_at)
                VALUES(?,?,'contributor','Review',?,'2026-10-20')''',
                (doc['id'], users[3]['id'], 'superseded' if n % 4 == 0 else 'assigned'))
        if n % 3 == 0:
            conn.execute('''INSERT INTO document_email_import(mailbox,message_id,payload_hash,document_id,
                received_at,attachments_json,created_at) VALUES('mail@example.test',?,'hash',?,
                '2026-10-20','[]','2026-10-20')''', (f'message-{n}', doc['id']))
        directive = conn.execute('''INSERT INTO document_directive(document_id,actor_id,text,created_at)
            VALUES(?,?,'Watershed instruction','2026-10-20')''', (doc['id'], users[0]['id'])).lastrowid
        conn.execute('INSERT INTO document_instruction_recipient VALUES(?,?)', (directive, users[3]['id']))
        conn.execute("INSERT INTO document_instruction_tag VALUES(?,'person',?)", (directive, users[3]['id']))
        if n % 2:
            conn.execute('INSERT INTO document_instruction_read VALUES(?,?,?)', (directive, users[3]['id'], '2026-10-20'))
        conn.execute('UPDATE document SET instruction_state=? WHERE id=?', ('pending' if n % 2 else 'routed', doc['id']))
        if state == 'closed':
            conn.execute('''INSERT INTO document_event(document_id,actor_id,action,detail_json,occurred_at,recorded_at)
                VALUES(?,?,'close','{}','2026-10-23T21:00:00','2026-10-23T21:00:00')''', (doc['id'], users[0]['id']))
        records.append(doc)
        conn.commit()
    # An actual merge: alias metadata can find the canonical record, once.
    target = register(conn, users[0], unit, 'OUT', subject='Alias target')
    source = register(conn, users[0], unit, 'OUT', subject='Needle alias receipt')
    docs.merge(conn, users[1], docs.merge_preview(conn, users[1], source['id'], target['id']), 'Duplicate')
    conn.commit()
    return conn, users + extra, records, target, source


@pytest.mark.parametrize('queue', QUEUES)
@pytest.mark.parametrize('query', ['', 'Needle', 'Watershed', 'alias receipt'])
def test_full_selection_matches_frozen_legacy_for_every_role(mixed, queue, query):
    conn, users, _, _, _ = mixed
    for user in users:
        previous = legacy_visible(conn, user, query, queue)
        current = docs.list_visible(conn, user, query, queue)
        assert ids(current) == ids(previous), (user['username'], queue, query)
        assert docs.count_visible(conn, user, query, queue) == len(previous)
        for old, new in zip(previous, current):
            assert old.get('search_source') == new.get('search_source')
            assert old.get('search_excerpt') == new.get('search_excerpt')


def test_pages_match_whole_result_without_repeats_including_aliases(mixed):
    conn, users, _, _, _ = mixed
    for user in users:
        for query in ('', 'Needle', 'alias'):
            expected = ids(legacy_visible(conn, user, query))
            found, before = [], 0
            for _ in range(30):
                page = docs.list_page(conn, user, query, before=before, limit=2)
                found += ids(page['documents'])
                assert page['total'] == len(expected)
                if not page['more']:
                    break
                assert page['next_before'] < before or before == 0
                before = page['next_before']
            else:
                pytest.fail('Page cursor failed to terminate')
            assert found == expected
            assert len(found) == len(set(found))


def test_full_totals_equal_original_metrics_not_just_first_page(mixed):
    conn, users, _, _, _ = mixed
    for user in users:
        for queue in ('all', 'review', 'archived'):
            previous = legacy_visible(conn, user, 'Needle', queue)
            page = docs.list_page(conn, user, 'Needle', queue, limit=2)
            assert page['metrics'] == legacy_metrics(conn, previous)
            assert page['missing_dates'] == sum(not doc['due_date'] for doc in previous)
            assert page['total'] == len(previous)


def test_permissions_filter_before_page_limit(registry):
    conn, users, unit, _ = registry
    public = seed_many(conn, users[0], unit, 65)
    seed_many(conn, users[0], unit, 90, subject='Hidden', visibility='restricted')
    page = docs.list_page(conn, users[4])  # technical admin has no implicit private grant
    assert len(page['documents']) == 30
    assert ids(page['documents']) == list(reversed(public))[:30]
    assert page['total'] == 65 and page['more']
    other = docs.list_page(conn, users[4], before=page['next_before'])
    assert ids(other['documents']) == list(reversed(public))[30:60]
    assert not set(ids(page['documents'])) & set(ids(other['documents']))


def test_new_records_do_not_shift_existing_older_page_cursor(registry):
    conn, users, unit, _ = registry
    original = seed_many(conn, users[0], unit, 65)
    first = docs.list_page(conn, users[4])
    added = seed_many(conn, users[0], unit, 3)
    older = docs.list_page(conn, users[4], before=first['next_before'])
    assert ids(older['documents']) == list(reversed(original))[30:60]
    assert older['total'] == 68
    assert ids(docs.list_page(conn, users[4])['documents'])[:3] == list(reversed(added))


def traced(conn, callback):
    statements = []
    conn.set_trace_callback(lambda sql: statements.append(sql) if sql.lstrip().upper().startswith(('SELECT', 'WITH')) else None)
    try:
        result = callback()
    finally:
        conn.set_trace_callback(None)
    return result, len(statements)


def test_first_page_query_count_and_loaded_rows_stay_bounded(registry, monkeypatch):
    conn, users, unit, _ = registry
    seed_many(conn, users[0], unit, 80)
    calls = []
    original = registry_reads.rows
    def measured(conn, sql, args=()):
        result = original(conn, sql, args)
        calls.append((sql, len(result)))
        return result
    monkeypatch.setattr(registry_reads, 'rows', measured)
    def no_per_record_check(*args, **kwargs):
        raise AssertionError('Registry must filter in SQL instead of checking each loaded record')
    monkeypatch.setattr(permissions, 'can_view', no_per_record_check)
    small, small_queries = traced(conn, lambda: docs.list_page(conn, users[4]))
    seed_many(conn, users[0], unit, 720)
    large, large_queries = traced(conn, lambda: docs.list_page(conn, users[4]))
    assert small['total'] == 80 and large['total'] == 800
    assert len(large['documents']) == 30
    assert large_queries == small_queries
    assert large_queries < 50
    assert all(count <= 31 for _, count in calls)
    assert any('LIMIT :registry_limit' in sql and count == 31 for sql, count in calls)


def test_search_pages_use_bounded_queries_without_loading_full_match_set(registry, monkeypatch):
    conn, users, unit, _ = registry
    seed_many(conn, users[0], unit, 80, subject='Searchable needle')
    def no_full_search(*args, **kwargs):
        raise AssertionError('Registry search must not load the complete FTS match set')
    import documents_search
    monkeypatch.setattr(documents_search, 'matches', no_full_search)
    small, queries = traced(conn, lambda: docs.list_page(conn, users[4], 'needle'))
    seed_many(conn, users[0], unit, 720, subject='Searchable needle')
    large, larger_queries = traced(conn, lambda: docs.list_page(conn, users[4], 'needle'))
    assert queries == larger_queries and larger_queries < 50
    assert large['total'] == 800 and small['total'] == 80
    assert len(large['documents']) == 30
    assert all(doc.get('search_source') == 'Record details' for doc in large['documents'])


def test_normal_older_page_uses_index_seek_without_sorting_the_register(registry):
    conn, users, unit, _ = registry
    seed_many(conn, users[0], unit, 80)
    selection = registry_reads.Selection(conn, users[4])
    statement, params = selection.page_statement(before=40, limit=31)
    plan = ' '.join(row[3] for row in conn.execute('EXPLAIN QUERY PLAN ' + statement, params))
    assert re.search(r'(?:rowid|id)<\?', plan), plan
    assert 'USE TEMP B-TREE FOR ORDER BY' not in plan, plan


def test_metadata_unicode_substrings_and_fts_search_still_match(registry):
    conn, users, unit, _ = registry
    doc = register(conn, users[0], unit, 'OUT', subject='Ｆｕｌｌ café Straße 100%_literal')
    conn.execute('INSERT INTO document_reference(document_id,kind,value) VALUES(?,?,?)',
                 (doc['id'], 'external', 'Important Reference'))
    conn.commit()
    for query in ('full', 'CAFÉ', 'strasse', '100%_', 'portant ref', '" OR 1=1 --', '   '):
        assert ids(docs.list_visible(conn, users[0], query)) == ids(legacy_visible(conn, users[0], query))


def test_actor_grants_and_seats_are_reloaded_between_pages(registry):
    conn, users, unit, _ = registry
    seed_many(conn, users[0], unit, 35, visibility='preverification', verified=False)
    grant(conn, users[3], 'records', unit)
    page = docs.list_page(conn, users[3], limit=2)
    assert page['more']
    conn.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=? AND role=?',
                 ('2026-10-21', users[3]['id'], 'records'))
    conn.commit()
    spoofed = {**users[3], 'role': 'admin'}
    denied = docs.list_page(conn, spoofed, before=page['next_before'])
    assert denied['total'] == 0 and denied['documents'] == []
    st.set_section_oic(conn, unit, users[3]['id'], set_by=users[1]['id'])
    assert docs.list_page(conn, users[3])['total'] == 35
    st.clear_section_oic(conn, unit)
    assert docs.list_page(conn, users[3])['total'] == 0
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[3]['id'],))
    conn.commit()
    with pytest.raises(permissions.Denied):
        docs.list_page(conn, users[3])


def test_explicit_restricted_access_revocation_applies_to_saved_cursor(registry):
    conn, users, unit, _ = registry
    keys = seed_many(conn, users[0], unit, 5, visibility='restricted')
    conn.executemany('INSERT INTO document_access VALUES(?,?,?)', [(key, users[3]['id'], 'test') for key in keys])
    conn.commit()
    page = docs.list_page(conn, users[3], limit=2)
    conn.execute('DELETE FROM document_access WHERE user_id=?', (users[3]['id'],))
    conn.commit()
    assert docs.list_page(conn, users[3], before=page['next_before'])['documents'] == []
    assert docs.count_visible(conn, users[3]) == 0


def test_migrated_assignment_requires_every_linked_record_to_remain_visible(registry):
    conn, users, unit, _ = registry
    target = register(conn, users[0], unit, 'OUT', subject='Shared-work release')
    secret = register(conn, users[0], unit, 'OUT', subject='Restricted linked reference', visibility='restricted')
    conn.execute("UPDATE document SET visibility='bureau',verification='verified',status='approved' WHERE id=?", (target['id'],))
    case = conn.execute('''INSERT INTO work_case(title,outcome,unit_id,creator_id,created_at,updated_at)
        VALUES('Work','Respond',?,?,'2026-10-20','2026-10-20')''', (unit, users[0]['id'])).lastrowid
    task = conn.execute('''INSERT INTO work_task(case_id,title,expected_output,unit_id,owner_id,creator_id,
        status,created_at,updated_at) VALUES(?,'Review','Response',?,?,?,'todo','2026-10-20','2026-10-20')''',
        (case, unit, users[3]['id'], users[0]['id'])).lastrowid
    conn.execute('''INSERT INTO work_legacy_document(document_id,case_id,actor_id,reason,source_revision,created_at)
        VALUES(?,?,?,'Moved',1,'2026-10-20')''', (target['id'], case, users[0]['id']))
    conn.executemany("INSERT INTO work_document VALUES(?,?,'reference',?,'2026-10-20')",
                     [(case, key, users[0]['id']) for key in (target['id'], secret['id'])])
    conn.commit()
    for queue in ('mine', 'release'):
        assert docs.list_visible(conn, users[3], queue=queue) == []
    conn.execute('INSERT INTO document_access VALUES(?,?,?)', (secret['id'], users[3]['id'], 'test'))
    conn.commit()
    for queue in ('mine', 'release'):
        assert ids(docs.list_visible(conn, users[3], queue=queue)) == [target['id']]
        assert ids(legacy_visible(conn, users[3], queue=queue)) == [target['id']]
    conn.execute("UPDATE work_task SET status='cancelled' WHERE id=?", (task,))
    conn.commit()
    assert docs.list_visible(conn, users[3], queue='release') == []
    assert docs.list_visible(conn, users[3], queue='mine') == []
    conn.execute("UPDATE work_task SET status='proposed',owner_id=NULL,proposed_owner_id=? WHERE id=?",
                 (users[3]['id'], task))
    conn.commit()
    # The compatibility assignment view shows the proposal, but that does not
    # make someone a confirmed participant in the migrated shared work.
    assert docs.list_visible(conn, users[3], queue='release') == []
    assert docs.list_visible(conn, users[3], queue='mine') == []


def test_alias_chains_inherit_terminal_permissions_and_cycles_fail_closed(registry):
    conn, users, unit, _ = registry
    target, middle, source = [register(conn, users[0], unit, 'OUT', subject=subject)
                              for subject in ('Secret terminal', 'Intermediate', 'Needle receipt')]
    conn.execute("UPDATE document SET visibility='restricted',canonical_id=NULL WHERE id=?", (target['id'],))
    conn.execute('UPDATE document SET canonical_id=? WHERE id=?', (target['id'], middle['id']))
    conn.execute('UPDATE document SET canonical_id=? WHERE id=?', (middle['id'], source['id']))
    conn.execute('INSERT INTO document_access VALUES(?,?,?)', (source['id'], users[3]['id'], 'alias-only'))
    conn.commit()
    assert docs.list_visible(conn, users[3], 'Needle') == []
    conn.execute('INSERT INTO document_access VALUES(?,?,?)', (target['id'], users[3]['id'], 'terminal'))
    conn.commit()
    assert ids(docs.list_visible(conn, users[3], 'Needle')) == ids(legacy_visible(conn, users[3], 'Needle')) == [middle['id']]
    conn.execute('UPDATE document SET canonical_id=? WHERE id=?', (source['id'], target['id']))
    conn.commit()
    assert docs.list_visible(conn, users[3], 'Needle') == []


def test_cursor_does_not_commit_callers_transaction(registry):
    conn, users, unit, _ = registry
    seed_many(conn, users[0], unit, 2)
    conn.execute("UPDATE document SET subject='Uncommitted edit'")
    assert conn.in_transaction
    assert len(docs.list_page(conn, users[0])['documents']) == 2
    assert conn.in_transaction
    conn.rollback()
    assert docs.list_page(conn, users[0])['documents'][0]['subject'] != 'Uncommitted edit'


def test_migrated_work_predicates_match_detail_authority_for_all_states(registry):
    conn, users, unit, _ = registry
    secret = register(conn, users[0], unit, 'OUT', visibility='restricted')
    alias = register(conn, users[0], unit, 'OUT')
    conn.execute('UPDATE document SET canonical_id=? WHERE id=?', (secret['id'], alias['id']))
    conn.commit()
    keys = []
    scenarios = [('todo', True, False, None), ('todo', True, False, secret['id']),
                 ('todo', True, False, alias['id']), ('cancelled', True, False, None),
                 ('proposed', False, False, None), ('todo', False, True, None),
                 ('todo', True, True, secret['id'])]
    for state, owner, lead, reference in scenarios:
        doc = register(conn, users[0], unit, 'OUT')
        conn.execute("UPDATE document SET visibility='bureau',verification='verified',status='approved',lead_id=? WHERE id=?",
                     (users[3]['id'] if lead else None, doc['id']))
        case = conn.execute('''INSERT INTO work_case(title,outcome,unit_id,creator_id,lead_id,created_at,updated_at)
            VALUES('Work','Respond',?,?,?,'2026-10-20','2026-10-20')''',
            (unit, users[0]['id'], users[3]['id'] if lead else None)).lastrowid
        conn.execute('''INSERT INTO work_task(case_id,title,expected_output,unit_id,owner_id,proposed_owner_id,
            creator_id,status,created_at,updated_at) VALUES(?,'Task','Respond',?,?,?,?,?,'2026-10-20','2026-10-20')''',
            (case, unit, users[3]['id'] if owner else None, users[3]['id'], users[0]['id'], state))
        conn.execute('''INSERT INTO work_legacy_document(document_id,case_id,actor_id,reason,source_revision,created_at)
            VALUES(?,?,?,'Moved',1,'2026-10-20')''', (doc['id'], case, users[0]['id']))
        for key in [doc['id']] + ([reference] if reference else []):
            conn.execute("INSERT INTO work_document VALUES(?,?,'reference',?,'2026-10-20')", (case, key, users[0]['id']))
        conn.commit()
        keys.append(doc['id'])
    for user in users:
        scope = permissions.RegistryScope(conn, user)
        sql = f'''SELECT d.id,{scope.work_sql('d')},{scope.release_sql('d')}
            FROM document d WHERE d.id IN (SELECT value FROM json_each(:test_ids))'''
        for key, can_work, can_release in conn.execute(sql, {**scope.params, 'test_ids': json.dumps(keys)}):
            doc = docs.raw(conn, key)
            assert bool(can_work) == bool(permissions.can_work(conn, user, doc))
            assert bool(can_release) == bool(permissions.can_release(conn, user, doc))


@pytest.mark.parametrize('before', ['bad', '-1', '1.5', str(2**64)])
def test_bad_cursor_is_clear_http_error(app_mod, viewer, before):
    response = viewer.get('/documents', params={'before': before})
    assert response.status_code == 400
    assert 'Invalid document page' in response.text


def test_invalid_live_dates_do_not_silently_change_queue_measures(registry):
    conn, users, unit, _ = registry
    doc = register(conn, users[0], unit, 'OUT')
    conn.execute("UPDATE document SET due_date='2026-02-30' WHERE id=?", (doc['id'],))
    conn.commit()
    with pytest.raises(ValueError):
        legacy_metrics(conn, legacy_visible(conn, users[0]))
    with pytest.raises(ValueError, match='Some document dates are invalid'):
        docs.list_page(conn, users[0])


def test_private_invalid_dates_are_not_used_in_another_users_totals(registry):
    conn, users, unit, _ = registry
    seed_many(conn, users[0], unit, 2)
    private = register(conn, users[0], unit, 'OUT', visibility='restricted')
    conn.execute("UPDATE document SET due_date='bad private date' WHERE id=?", (private['id'],))
    conn.commit()
    page = docs.list_page(conn, users[4])
    assert page['total'] == 2 and page['metrics']['unknown_deadline'] == 2


def test_http_pagination_preserves_search_and_export_is_complete(app_mod, viewer, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    unit = conn.execute('SELECT id FROM org_unit LIMIT 1').fetchone()[0]
    public = seed_many(conn, user, unit, 36, subject='Review café & follow-up')
    first = viewer.get('/documents', params={'queue': 'OUT', 'q': 'café & follow-up'})
    assert first.status_code == 200
    links = re.findall(r'href="/documents/(\d+)"', first.text)
    assert len(links) == 30
    assert '36 matching records you can access' in first.text
    older = html.unescape(re.search(r'href="([^"]+)" rel="next"', first.text)[1])
    params = parse_qs(urlsplit(older).query)
    assert params['q'] == ['café & follow-up'] and params['queue'] == ['OUT']
    second = viewer.get(older)
    assert len(re.findall(r'href="/documents/(\d+)"', second.text)) == 6
    assert 'rel="next"' not in second.text
    assert 'Newest records' in second.text
    def no_unused_bodies(*args, **kwargs):
        raise AssertionError('CSV must not fetch excerpts it never exports')
    monkeypatch.setattr(registry_reads.Selection, '_snippets', no_unused_bodies)
    full = viewer.get('/documents/export.csv', params={'queue': 'OUT', 'q': 'café & follow-up'})
    import csv, io
    records = list(csv.DictReader(io.StringIO(full.text)))
    assert len(records) == len(public)
    assert len({item['number'] for item in records}) == 36
    conn.close()


def test_complete_http_page_query_growth_is_bounded(app_mod, viewer, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    unit = conn.execute('SELECT id FROM org_unit LIMIT 1').fetchone()[0]
    st.set_setting(conn, 'documents.enabled', '1')
    seed_many(conn, user, unit, 80)
    original = st.connect
    statements = []
    def observed(*args, **kwargs):
        opened = original(*args, **kwargs)
        opened.set_trace_callback(lambda sql: statements.append(sql) if sql.lstrip().upper().startswith(('SELECT', 'WITH')) else None)
        return opened
    monkeypatch.setattr(st, 'connect', observed)
    viewer.get('/documents')  # consistent warm request state
    statements.clear()
    assert viewer.get('/documents').status_code == 200
    small = len(statements)
    seed_many(conn, user, unit, 720)
    statements.clear()
    page = viewer.get('/documents')
    assert page.status_code == 200
    assert '800 matching records you can access' in page.text
    assert len(statements) <= small + 5
    conn.close()
