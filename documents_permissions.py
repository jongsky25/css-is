"""One document visibility predicate for detail, queues, exports, jobs and search."""
import json
import storage as st
from documents_storage import rows


class Denied(ValueError):
    pass


def actor(conn, user):
    # Trust the session's account ID, never its claimed role, directory or grants.
    found = st.get_admin_user_by_id(conn, user.get('id')) if isinstance(user, dict) else None
    if not found or not found.get('active'):
        raise Denied('An active staff account is required.')
    return found


def scope_contains(conn, parent, child):
    if parent is None:
        return True
    paths = {r[0]: r[1] for r in conn.execute('SELECT id,path FROM org_unit WHERE id IN (?,?)', (parent, child))}
    return parent in paths and child in paths and (paths[child] == paths[parent] or paths[child].startswith(paths[parent] + '/'))


def has_role(conn, user, role, unit_id=None):
    return any(scope_contains(conn, r['unit_id'], unit_id) for r in rows(conn,
        'SELECT unit_id FROM document_role_grant WHERE user_id=? AND role=? AND revoked_at IS NULL', (user['id'], role)))


def seats(conn, user):
    result = []
    for unit in rows(conn, "SELECT id,level,path FROM org_unit WHERE level IN ('division','bureau')"):
        oic = conn.execute('SELECT admin_user_id FROM section_oic WHERE org_unit_id=?', (unit['id'],)).fetchone()
        if user['id'] in st.org_unit_chiefs(conn, unit['id']) or (oic and oic[0] == user['id']):
            result.append({**unit, 'oic': bool(oic and oic[0] == user['id'])})
    return result


def director(conn, user):
    return bool(st._org_accounts_at_rank(conn, 3) and user['id'] in st._org_accounts_at_rank(conn, 3)) or any(s['level'] == 'bureau' for s in seats(conn, user))


def officer(conn, user, doc):
    evaluation=json.loads(doc.get('matches_json') or '{}')
    concerned={doc['unit_id']} | set(evaluation.get('unit_ids',[]) if isinstance(evaluation,dict) else [])
    return any(has_role(conn,user,'records',unit) for unit in concerned) or director(conn,user) or any(
        scope_contains(conn,s['id'],unit) for s in seats(conn,user) for unit in concerned)


def can_view(conn, user, doc):
    if not doc:
        return False
    try:
        user = actor(conn, user)
    except Denied:
        return False
    if doc['canonical_id']:
        target = rows(conn, 'SELECT * FROM document WHERE id=?', (doc['canonical_id'],))
        return bool(target and can_view(conn, user, target[0]))
    explicit = conn.execute('SELECT 1 FROM document_access WHERE document_id=? AND user_id=?', (doc['id'], user['id'])).fetchone()
    if doc['visibility'] == 'restricted':
        return bool(explicit)  # Even a Director or technical admin needs explicit access.
    if doc['verification'] == 'verified' and doc['visibility'] == 'bureau':
        return True
    return bool(explicit or doc['creator_id'] == user['id'] or officer(conn, user, doc))


def require_view(conn, user, doc):
    if not can_view(conn, user, doc):
        raise Denied('Document not found or unavailable to you.')


def assigned(conn, user, doc):
    migration = conn.execute('SELECT case_id FROM work_legacy_document WHERE document_id=?',(doc['id'],)).fetchone()
    if migration:
        import work
        try:
            work.get(conn, user, migration[0])
        except Denied:
            return False
        return doc['lead_id']==user['id'] or bool(conn.execute(
            "SELECT 1 FROM work_task WHERE case_id=? AND owner_id=? AND status<>'cancelled'",
            (migration[0],user['id'])).fetchone())
    return bool(conn.execute("SELECT 1 FROM document_assignment_effective WHERE document_id=? AND user_id=? AND status<>'superseded'",
                             (doc['id'], user['id'])).fetchone())


def can_work(conn, user, doc):
    return doc['creator_id'] == user['id'] or doc['lead_id'] == user['id'] or officer(conn, user, doc) or assigned(conn, user, doc)


def can_release(conn, user, doc):
    return officer(conn, user, doc) or assigned(conn, user, doc)
