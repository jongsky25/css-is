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


class RegistryScope:
    """Current authority compiled once for a read snapshot, never cached across requests.

    SQL versions below preserve the existing detail predicates, including strict
    explicit access to restricted records and the linked-work visibility check.
    Directory/authority policy continues to come from the existing seat helpers.
    """

    def __init__(self, conn, user):
        self.user = actor(conn, user)
        self.uid = self.user['id']
        current_seats = seats(conn, self.user)
        self.is_director = (self.uid in st._org_accounts_at_rank(conn, 3)
                            or any(s['level'] == 'bureau' for s in current_seats))
        paths = dict(conn.execute('SELECT id,path FROM org_unit'))
        grants = rows(conn, '''SELECT role,unit_id FROM document_role_grant
            WHERE user_id=? AND revoked_at IS NULL''', (self.uid,))

        def covered(parents):
            return sorted(child for child, path in paths.items() if any(
                parent in paths and (path == paths[parent] or path.startswith(paths[parent] + '/'))
                for parent in parents if parent is not None))

        records = [g['unit_id'] for g in grants if g['role'] == 'records']
        workflow = [g['unit_id'] for g in grants if g['role'] == 'workflow_admin']
        self.officer_all = self.is_director or None in records
        self.workflow_all = None in workflow
        self.params = {'registry_actor': self.uid,
                       'registry_officer_units': json.dumps(covered(records + [s['id'] for s in current_seats])),
                       'registry_workflow_units': json.dumps(covered(workflow))}

    def officer_sql(self, alias, *, concerned=True):
        if self.officer_all:
            return '1'
        own = f'{alias}.unit_id IN (SELECT value FROM json_each(:registry_officer_units))'
        if not concerned:
            return f'COALESCE(({own}),0)'
        # The detail predicate only treats a dictionary's unit_ids as concerned
        # units. JSON strings must not turn into integer authority grants.
        matching = f'''EXISTS (SELECT 1 FROM json_each(CASE
            WHEN json_valid({alias}.matches_json) THEN CASE
              WHEN json_type({alias}.matches_json,'$.unit_ids')='array'
              THEN json_extract({alias}.matches_json,'$.unit_ids') ELSE '[]' END
            ELSE '[]' END) unit
            WHERE unit.type IN ('integer','real','true','false')
              AND unit.value IN (SELECT value FROM json_each(:registry_officer_units)))'''
        return f'COALESCE(({own} OR {matching}),0)'

    def workflow_sql(self, alias):
        return '1' if self.workflow_all else (
            f'{alias}.unit_id IN (SELECT value FROM json_each(:registry_workflow_units))')

    def _base_view_sql(self, alias):
        explicit = f'''EXISTS (SELECT 1 FROM document_access access
            WHERE access.document_id={alias}.id AND access.user_id=:registry_actor)'''
        return f'''COALESCE((CASE WHEN {alias}.visibility='restricted' THEN {explicit}
            ELSE ({explicit} OR {alias}.creator_id=:registry_actor
              OR ({alias}.verification='verified' AND {alias}.visibility='bureau')
              OR {self.officer_sql(alias)}) END),0)'''

    def view_sql(self, alias):
        # UNION (not UNION ALL) terminates a damaged merge cycle. A missing or
        # cyclic canonical target has no permitted terminal record: fail closed.
        return f'''({alias}.id IS NOT NULL AND CASE WHEN {alias}.canonical_id IS NULL
            THEN {self._base_view_sql(alias)} ELSE EXISTS (
              WITH RECURSIVE registry_chain AS (
                SELECT * FROM document WHERE id={alias}.canonical_id
                UNION SELECT parent.* FROM document parent JOIN registry_chain child
                  ON parent.id=child.canonical_id)
              SELECT 1 FROM registry_chain registry_root
              WHERE registry_root.canonical_id IS NULL AND {self._base_view_sql('registry_root')}
            ) END)'''

    def assignment_ctes(self):
        """Flat read relations avoid deep SQL nesting on deployment SQLite builds."""
        case_member = f'''(wc.creator_id=:registry_actor OR wc.lead_id=:registry_actor
            OR {self.officer_sql('wc', concerned=False)} OR EXISTS (
              SELECT 1 FROM work_task participant WHERE participant.case_id=wc.id
                AND ((participant.owner_id=:registry_actor AND participant.status<>'cancelled')
                     OR {self.officer_sql('participant', concerned=False)})))'''
        return f'''registry_work_candidates AS (
            SELECT wc.id AS case_id,migration.document_id
              FROM work_legacy_document migration JOIN work_case wc ON wc.id=migration.case_id
              JOIN document target ON target.id=migration.document_id
              WHERE {case_member}
                AND (target.lead_id=:registry_actor OR EXISTS (
                  SELECT 1 FROM work_task owned WHERE owned.case_id=wc.id
                    AND owned.owner_id=:registry_actor AND owned.status<>'cancelled'))),
            registry_visible_references AS (
              SELECT link.case_id,link.document_id FROM work_document link
                JOIN registry_work_candidates candidate ON candidate.case_id=link.case_id
                JOIN document linked_doc ON linked_doc.id=link.document_id
              WHERE {self.view_sql('linked_doc')}),
            registry_assigned AS (
              SELECT assignment.document_id FROM document_assignment assignment
              WHERE assignment.user_id=:registry_actor AND assignment.status<>'superseded'
                AND NOT EXISTS (SELECT 1 FROM work_legacy_document migration
                                WHERE migration.document_id=assignment.document_id)
              UNION ALL
              SELECT candidate.document_id FROM registry_work_candidates candidate
              WHERE NOT EXISTS (
                SELECT 1 FROM work_document link WHERE link.case_id=candidate.case_id
                  AND NOT EXISTS (SELECT 1 FROM registry_visible_references permitted
                    WHERE permitted.case_id=link.case_id AND permitted.document_id=link.document_id)))'''

    def assigned_sql(self, alias):
        return f'''EXISTS (SELECT 1 FROM registry_assigned assignment
                          WHERE assignment.document_id={alias}.id)'''

    def work_sql(self, alias):
        return f'''({alias}.creator_id=:registry_actor OR {alias}.lead_id=:registry_actor
                    OR {self.officer_sql(alias)} OR {self.assigned_sql(alias)})'''

    def release_sql(self, alias):
        return f'({self.officer_sql(alias)} OR {self.assigned_sql(alias)})'
