"""Read-only, bounded table pages over the existing authorized registry selection."""
import math

import documents_permissions as permissions
from documents_registry import PAGE_SIZE, Selection, snapshot
from documents_storage import rows


QUEUES = {'all', 'IN', 'OUT', 'verification', 'review', 'release', 'mine',
          'mentions', 'unassigned', 'archived', 'gmail', 'gmail_review', 'instruction'}
STATUSES = ('registered', 'draft', 'in_action', 'in_review', 'changes_requested',
            'approved', 'ready_to_release', 'released', 'awaiting_acknowledgment',
            'awaiting_external', 'closed', 'cancelled')
VERIFICATIONS = ('pending', 'verified', 'needs_correction')
SORTS = {'registered': 'selected.sort_id', 'number': 'd.number COLLATE NOCASE',
         'subject': 'd.subject COLLATE NOCASE', 'verification': 'd.verification',
         'status': 'd.status', 'due_date': 'NULLIF(d.due_date,\'\')',
         'lead': "COALESCE(u.username,'') COLLATE NOCASE"}


def page(conn, user, params):
    queue, query = params.get('queue', 'all'), params.get('q', '')
    sort, direction = params.get('sort', 'registered'), params.get('dir', 'desc')
    status, verification = params.get('status', ''), params.get('verification', '')
    if (queue not in QUEUES or sort not in SORTS or direction not in ('asc', 'desc')
            or status not in ('', *STATUSES) or verification not in ('', *VERIFICATIONS)
            or len(query) > 120):
        raise ValueError('Invalid table options. Reset the table and try again.')
    try:
        number = int(params.get('page', '1'))
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Invalid table page.') from None
    if not 1 <= number <= 1_000_000:
        raise ValueError('Invalid table page.')

    with snapshot(conn):
        selection = Selection(conn, user, '' if queue == 'instruction' else query, queue)
        if queue == 'instruction' and not selection.scope.is_director:
            raise permissions.Denied('This inbox is for the Director or bureau OIC.')
        where = ' AND '.join(['1'] + (["d.status=:grid_status"] if status else [])
                             + (["d.verification=:grid_verification"] if verification else []))
        values = {**selection.params, 'grid_status': status, 'grid_verification': verification}
        source = (selection.read_ctes() + ' SELECT {columns} FROM registry_selected selected '
                  'JOIN document d ON d.id=selected.id LEFT JOIN admin_user u ON u.id=d.lead_id '
                  f'WHERE {where}')
        total = conn.execute(source.format(columns='COUNT(*)'), values).fetchone()[0]
        last_page = max(1, math.ceil(total / PAGE_SIZE))
        # A concurrent deletion or permission change may remove the requested last page.
        number = min(number, last_page)
        values.update(grid_limit=PAGE_SIZE, grid_offset=(number - 1) * PAGE_SIZE)
        # Sort expressions/directions are allowlisted, never interpolated from user input.
        order = SORTS[sort] + ' ' + direction.upper()
        if sort == 'due_date':
            order = "(d.due_date IS NULL OR d.due_date='') ASC," + order
        order += ',selected.sort_id DESC'
        columns = '''d.id,d.number,d.subject,d.verification,d.status,d.due_date,
            d.archived_at,d.reconcile,COALESCE(u.username,'Unresolved') AS lead,
            selected.sort_id AS registry_sort_id,
            EXISTS (SELECT 1 FROM document_email_import i WHERE i.document_id=d.id) AS gmail_imported'''
        documents = rows(conn, source.format(columns=columns) +
                         f' ORDER BY {order} LIMIT :grid_limit OFFSET :grid_offset', values)
        # Reuse the registry's page-only snippets and current indexed-file access checks.
        if documents and selection.expression:
            selection._snippets(conn, documents)
        for doc in documents:
            doc['registered'] = doc.pop('registry_sort_id')
        return {'data': documents, 'last_page': last_page, 'last_row': total, 'page': number}
