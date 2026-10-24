"""Groups count and order the authorized result before pagination, sharing export scope."""
import csv
import io

import pytest

import documents_grid as grid
from tests.test_documents import registry
from tests.test_document_registry_pagination import seed_many
from tests.test_document_registry_views import state, create


def test_workflow_groups_span_pages_and_export_even_with_hidden_workflow(registry):
    conn, users, unit, _ = registry
    ids = seed_many(conn, users[0], unit, 65, subject='Groupneedle')
    hidden = seed_many(conn, users[0], unit, 5, subject='Groupneedle hidden', visibility='restricted')
    conn.execute("UPDATE document SET status='in_action',due_date='2026-11-15'")
    conn.executemany("UPDATE document SET status='draft' WHERE id=?", [(i,) for i in ids[::2]])
    conn.commit()
    params = {'q': 'Groupneedle', 'group_by': 'status', 'sort': 'registered', 'dir': 'asc',
              'due_from': '2026-11-01', 'due_to': '2026-11-30'}
    pages = [grid.page(conn, users[4], {**params, 'page': str(n)}) for n in (1, 2, 3)]
    expected = ids[::2] + ids[1::2]
    assert [r['id'] for p in pages for r in p['data']] == expected
    assert all(p['groups'] == [{'group_key':'draft','group_label':'draft','count':33},
                               {'group_key':'in_action','group_label':'in action','count':32}] for p in pages)
    assert all(p['last_row'] == 65 and p['group_by'] == 'status' for p in pages)
    assert not set(hidden) & set(expected)
    content, count = grid.export_csv(conn, users[4], {**params, 'columns': 'number'})
    data = list(csv.reader(io.StringIO(content.removeprefix('\ufeff'))))
    assert count == 65 and data[0] == ['Group: Workflow', 'Number']
    assert [r[1] for r in data[1:]] == [f'REG-{i}' for i in expected]
    assert [r[0] for r in data[1:]] == ['draft'] * 33 + ['in action'] * 32
    filtered = grid.page(conn, users[4], {**params, 'status':'draft'})
    assert filtered['groups'] == pages[0]['groups'][:1]
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?", (ids[0],));conn.commit()
    assert grid.page(conn, users[4], params)['groups'][0]['count'] == 32
    assert grid.export_csv(conn, users[4], {**params, 'columns':'number'})[1] == 64


def test_lead_groups_use_identity_and_safe_labels_and_saved_view_defaults(registry):
    conn, users, unit, _ = registry
    ids = seed_many(conn, users[0], unit, 4)
    # Historical inactive leads remain separate groups; label is untrusted text.
    conn.execute("UPDATE admin_user SET username='=HYPERLINK(\"x\")',active=0 WHERE id=?", (users[1]['id'],))
    conn.execute('UPDATE document SET lead_id=? WHERE id=?', (users[1]['id'], ids[0]))
    conn.execute('UPDATE document SET lead_id=? WHERE id=?', (users[2]['id'], ids[1]))
    conn.execute('UPDATE document SET lead_id=NULL WHERE id IN (?,?)', ids[2:]);conn.commit()
    params = {'group_by':'lead', 'sort':'registered', 'dir':'asc'}
    page = grid.page(conn, users[0], params)
    counts = {r['group_key']: r['count'] for r in page['groups']}
    assert counts == {str(users[1]['id']):1, str(users[2]['id']):1, '0':2}
    assert page['data'][0]['id'] == ids[0]
    content, count = grid.export_csv(conn, users[0], {**params,'columns':'number'})
    data = list(csv.reader(io.StringIO(content.removeprefix('\ufeff'))))
    assert data[0] == ['Group: Assigned lead','Number'] and count == 4
    assert data[1][0].startswith("'=HYPERLINK")
    saved = create(conn,users[0],'By lead',group_by='lead')
    assert saved['state']['group_by'] == 'lead'
    assert grid.view_state(state())['group_by'] == ''
    assert grid.page(conn,users[0],{'group_by':'lead','lead_id':'unresolved'})['groups'] == [
        {'group_key':'0','group_label':'Unresolved','count':2}]
    empty=grid.page(conn,users[0],{'group_by':'lead','q':'No such group'})
    assert empty['groups'] == [] and empty['last_row'] == 0
    ungrouped=grid.page(conn,users[0],{})
    assert ungrouped['groups'] == [] and 'group_key' not in ungrouped['data'][0]


@pytest.mark.parametrize('invalid', ['workflow','lead_id','d.status;DROP TABLE document',None,True,[],{}])
def test_grouping_allowlist_is_shared_by_grid_export_and_preferences(registry,invalid):
    conn,users,_,_=registry
    for operation in (lambda:grid.page(conn,users[0],{'group_by':invalid}),
                      lambda:grid.export_csv(conn,users[0],{'group_by':invalid}),
                      lambda:grid.view_state(state(group_by=invalid))):
        with pytest.raises(ValueError,match='Group by'):
            operation()
