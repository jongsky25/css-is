"""Permission-aware registry reads. Filter before LIMIT, fetch only page records.

Exports/legacy callers can still request the complete permitted result set.
Authority is resolved per database snapshot; page cursors carry no authority.
"""
from contextlib import contextmanager
from datetime import date, datetime
import json
import sqlite3

import documents_permissions as permissions
import documents_rules as rules
import documents_search as search
from documents_storage import rows
import tzutil as tz

PAGE_SIZE = 30
MAX_PAGE_SIZE = 100


@contextmanager
def snapshot(conn):
    conn.execute('SAVEPOINT document_registry_read')
    try:
        yield
    except BaseException:
        conn.execute('ROLLBACK TO document_registry_read')
        raise
    finally:
        conn.execute('RELEASE document_registry_read')


def cursor(value):
    try:
        parsed = int(value or 0)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Invalid document page. Open the newest records and try again.') from None
    if parsed < 0 or parsed > 9223372036854775807:
        raise ValueError('Invalid document page. Open the newest records and try again.')
    return parsed


class Selection:
    def __init__(self, conn, user, query='', queue='all'):
        self.scope = permissions.RegistryScope(conn, user)
        self.query, self.queue = query, queue
        self.params = dict(self.scope.params)
        self.expression = search._match_expression(query) if query else None
        conn.create_function('registry_normalize', 1, rules.normalize, deterministic=True)
        self.sql = self._select_sql()

    def _queue_sql(self):
        s, scope = 's', self.scope
        return {
            'instruction': ("s.instruction_state='pending' AND s.status NOT IN ('closed','cancelled')"
                            if scope.is_director else '0'),
            'gmail': "EXISTS (SELECT 1 FROM document_email_import i WHERE i.document_id=s.id)",
            'gmail_review': ("EXISTS (SELECT 1 FROM document_email_import i WHERE i.document_id=s.id) "
                             "AND s.verification<>'verified' AND s.status NOT IN ('closed','cancelled') "
                             f"AND {scope.officer_sql(s)}"),
            'IN': "s.direction='IN'",
            'OUT': "s.direction='OUT'",
            'verification': f"s.verification<>'verified' AND {scope.officer_sql(s)}",
            'review': "s.status='in_review' AND s.reviewer_id=:registry_actor",
            'release': f"s.status IN ('approved','ready_to_release') AND {scope.release_sql(s)}",
            'mine': f"s.status NOT IN ('closed','cancelled') AND {scope.work_sql(s)}",
            'mentions': '''EXISTS (SELECT 1 FROM document_directive x
                JOIN document_instruction_recipient r ON r.directive_id=x.id
                LEFT JOIN document_instruction_read seen ON seen.directive_id=x.id AND seen.user_id=r.user_id
                WHERE x.document_id=s.id AND r.user_id=:registry_actor AND seen.directive_id IS NULL
                  AND EXISTS (SELECT 1 FROM document_instruction_tag t WHERE t.directive_id=x.id))''',
            'unassigned': 's.lead_id IS NULL',
        }.get(self.queue, '1')

    def _select_sql(self):
        scope = self.scope
        archived = (f's.archived_at IS NOT NULL AND {scope.workflow_sql("s")}'
                    if self.queue == 'archived' else 's.archived_at IS NULL')
        where = [scope.view_sql('s'), f'({archived})']
        queue = self._queue_sql()
        if not self.query:
            # Common path: no grouping, no FTS bodies, no canonical-chain scan.
            return f'''SELECT s.id,s.id AS sort_id FROM document s
                WHERE s.canonical_id IS NULL AND {' AND '.join(where)} AND ({queue})'''

        self.params['registry_query'] = rules.normalize(self.query)
        fts = '0'
        if self.expression:
            self.params['registry_fts'] = self.expression
            fts = '''s.canonical_id IS NULL AND s.id IN (
                SELECT f.document_id FROM document_search_fts f
                WHERE document_search_fts MATCH :registry_fts AND ''' + search.file_access_sql('f', ':registry_actor') + ')'
        metadata = '''instr(registry_normalize(s.number || ' ' || s.subject || ' ' || s.sender || ' ' ||
            COALESCE((SELECT group_concat(value,' ') FROM (
              SELECT value FROM document_reference WHERE document_id=s.id ORDER BY id)),'')),:registry_query)>0'''
        where.append(f'(({metadata}) OR ({fts}))')
        if self.queue in ('gmail', 'gmail_review'):
            # These queues have always excluded merged source receipts entirely.
            where.append('s.canonical_id IS NULL')
            where.append(f'({queue})')
        else:
            # Preserve legacy alias lookup semantics: matching a merged receipt
            # opens its direct canonical record. It must still be readable.
            where.append(f'(s.canonical_id IS NOT NULL OR ({queue}))')
            if self.queue == 'instruction':
                where.append("s.instruction_state='pending' AND s.status NOT IN ('closed','cancelled')")
                if not scope.is_director:
                    where.append('0')
        # The first matching source in descending source-ID order wins, exactly
        # as in the previous list. Seek after deduplication to prevent repeats.
        return f'''SELECT COALESCE(s.canonical_id,s.id) AS id,MAX(s.id) AS sort_id
            FROM document s WHERE {' AND '.join(where)} GROUP BY COALESCE(s.canonical_id,s.id)'''

    def page_statement(self, *, before=0, limit=None):
        params = {**self.params, 'registry_before': before}
        seek = 'selected.sort_id<:registry_before' if before else '1'
        sql = f'''WITH registry_selected AS ({self.sql})
            SELECT d.*,selected.sort_id AS registry_sort_id,
              EXISTS (SELECT 1 FROM document_email_import i WHERE i.document_id=d.id) AS gmail_imported
            FROM registry_selected selected JOIN document d ON d.id=selected.id
            WHERE {seek}
            ORDER BY selected.sort_id DESC'''
        if limit is not None:
            sql += ' LIMIT :registry_limit'
            params['registry_limit'] = limit
        return sql, params

    def fetch(self, conn, *, before=0, limit=None, snippets=True):
        sql, params = self.page_statement(before=before, limit=limit)
        documents = rows(conn, sql, params)
        if snippets and documents and self.expression:
            self._snippets(conn, documents)
        return documents

    def _snippets(self, conn, documents):
        # Only fetch one source body for each displayed record, not all FTS hits.
        ids = [doc['id'] for doc in documents if doc['id'] == doc['registry_sort_id']]
        if not ids:
            return
        sql = '''WITH matched AS MATERIALIZED (
            SELECT f.document_id,f.source_type,f.body,f.rowid AS source_row,rank AS score
            FROM document_search_fts f WHERE document_search_fts MATCH :registry_fts
              AND f.document_id IN (SELECT value FROM json_each(:registry_page_ids))
              AND ''' + search.file_access_sql('f', ':registry_actor') + '''), numbered AS (
            SELECT *,row_number() OVER (PARTITION BY document_id ORDER BY score,source_row) AS position FROM matched)
            SELECT document_id,source_type,body FROM numbered WHERE position=1'''
        found = {doc_id: (kind, body or '') for doc_id, kind, body in conn.execute(
            sql, {**self.params, 'registry_page_ids': json.dumps(ids)})}
        for doc in documents:
            if doc['id'] == doc['registry_sort_id'] and doc['id'] in found:
                kind, body = found[doc['id']]
                doc['search_source'] = search.LABELS[kind]
                doc['search_excerpt'] = search.excerpt(body, self.query)

    def count(self, conn):
        return conn.execute(f'SELECT COUNT(*) FROM ({self.sql})', self.params).fetchone()[0]

    def totals(self, conn, *, today=None):
        today = today or tz.today_local()
        soon = rules.shift(conn, today, 3)

        def elapsed(created, closed):
            if closed is None:
                return None
            return (datetime.fromisoformat(closed) - datetime.fromisoformat(created)).total_seconds() / 86400

        def due_day(value):
            return date.fromisoformat(value).isoformat() if value else None

        conn.create_function('registry_elapsed_days', 2, elapsed, deterministic=True)
        conn.create_function('registry_due_day', 1, due_day, deterministic=True)
        sql = f'''WITH registry_selected AS ({self.sql}), measured AS (
            SELECT d.*,d.status NOT IN ('closed','cancelled') AS live,
              CASE WHEN d.status NOT IN ('closed','cancelled') THEN registry_due_day(d.due_date) END AS live_due_day,
              EXISTS (SELECT 1 FROM document_assignment_effective a
                WHERE a.document_id=d.id AND a.status IN ('proposed','assigned')) AS unacknowledged,
              CASE WHEN d.status='closed' THEN registry_elapsed_days(d.created_at,(
                SELECT e.occurred_at FROM document_event e
                WHERE e.document_id=d.id AND e.action='close' ORDER BY e.id DESC LIMIT 1)) END AS days
            FROM registry_selected selected JOIN document d ON d.id=selected.id)
            SELECT COUNT(*) AS total,COALESCE(SUM(due_date IS NULL OR due_date=''),0) AS missing_dates,
              COALESCE(SUM(live AND lead_id IS NULL),0) AS unassigned,
              COALESCE(SUM(unacknowledged),0) AS unacknowledged,
              COALESCE(SUM(live AND live_due_day>=:registry_today AND live_due_day<=:registry_soon),0) AS due_soon,
              COALESCE(SUM(live AND live_due_day<:registry_today),0) AS overdue,
              COALESCE(SUM(status='in_review'),0) AS review,
              COALESCE(SUM(status IN ('approved','ready_to_release')),0) AS release,
              COALESCE(SUM(live AND (due_date IS NULL OR due_date='')),0) AS unknown_deadline,
              COUNT(days) AS known_turnaround,
              COALESCE(SUM(status='closed' AND days IS NULL),0) AS unknown_turnaround,
              AVG(days) AS average_calendar_days FROM measured'''
        try:
            totals = rows(conn, sql, {**self.params, 'registry_today': today.isoformat(),
                                      'registry_soon': soon.isoformat()})[0]
        except sqlite3.OperationalError as exc:
            if 'user-defined function raised exception' in str(exc):
                raise ValueError('Some document dates are invalid. Correct them before calculating register measures.') from None
            raise
        metrics = {key: value for key, value in totals.items() if key not in ('total', 'missing_dates')}
        if metrics['average_calendar_days'] is not None:
            metrics['average_calendar_days'] = round(metrics['average_calendar_days'], 2)
        return totals['total'], totals['missing_dates'], metrics


def page(conn, user, query='', queue='all', *, before=0, limit=PAGE_SIZE, totals=True, snippets=True):
    before = cursor(before)
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError('Invalid document page size.')
    with snapshot(conn):
        selection = Selection(conn, user, '' if queue == 'instruction' else query, queue)
        if queue == 'instruction' and not selection.scope.is_director:
            raise permissions.Denied('This inbox is for the Director or bureau OIC.')
        documents = selection.fetch(conn, before=before, limit=limit + 1, snippets=snippets)
        more = len(documents) > limit
        documents = documents[:limit]
        result = {'documents': documents, 'more': more, 'before': before,
                  'next_before': documents[-1]['registry_sort_id'] if more else None}
        if totals:
            result['total'], result['missing_dates'], result['metrics'] = selection.totals(conn)
        return result


def list_visible(conn, user, query='', queue='all', *, snippets=True):
    with snapshot(conn):
        return Selection(conn, user, query, queue).fetch(conn, snippets=snippets)


def count_visible(conn, user, query='', queue='all'):
    with snapshot(conn):
        return Selection(conn, user, query, queue).count(conn)
