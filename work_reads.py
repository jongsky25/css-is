"""Bounded shared-work reads; authorization precedes seek/limit in one snapshot."""
import documents_permissions as permissions
from documents_registry import cursor, snapshot
from documents_storage import rows
import work


def page(conn, user, *, before=0, limit=25):
    before = cursor(before)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid work page size.')
    with snapshot(conn):
        scope = permissions.RegistryScope(conn, user)
        selected = rows(conn, f'''SELECT wc.* FROM work_case wc
            WHERE {scope.work_view_sql('wc')} AND (:before=0 OR wc.id<:before)
            ORDER BY wc.id DESC LIMIT :limit''', {**scope.params, 'before': before, 'limit': limit + 1})
        more = len(selected) > limit
        selected = selected[:limit]
        return selected, selected[-1]['id'] if more else None


def tasks_page(conn, user, case_id, *, before=0, limit=25):
    before = cursor(before)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid task page size.')
    with snapshot(conn):
        # Case visibility is the UI policy for every contribution in that case.
        work.get(conn, user, case_id)
        selected = rows(conn, '''SELECT * FROM work_task WHERE case_id=? AND (?=0 OR id<?)
            ORDER BY id DESC LIMIT ?''', (case_id, before, before, limit + 1))
        more = len(selected) > limit
        selected = selected[:limit]
        return selected, selected[-1]['id'] if more else None


def task(conn, user, case_id, task_id):
    work.get(conn, user, case_id)
    selected = rows(conn, 'SELECT * FROM work_task WHERE id=? AND case_id=?', (task_id, case_id))
    if not selected:
        raise permissions.Denied('Task not found or unavailable to you.')
    return selected[0]
