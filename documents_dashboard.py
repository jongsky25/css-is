"""Aggregate the authorized registry snapshot; charts never receive record details."""
from urllib.parse import urlencode

import documents_grid as grid
from documents_storage import rows
import tzutil as tz

QUEUE_LABELS = [('all','All documents'),('mine','My document register'),('IN','Incoming'),('OUT','Outgoing'),
                ('verification','For verification'),('review','For review'),('release','For release'),
                ('mentions','Instructions for me'),('unassigned','Unassigned'),('gmail','From Gmail'),
                ('gmail_review','Gmail: needs verification'),('archived','Archive'),('instruction','For my instruction')]
DEADLINES = [('overdue','Overdue'),('due_soon','Due soon (including today)'),
             ('scheduled','Later deadlines'),('unknown','Unknown deadline'),('inactive','Closed or cancelled')]


MAX_PRESENTATION_LEADS = 1_000


def report(conn, user, params, *, presentation=False):
    # The dashboard has an explicit queue/search scope, independent of draft grid controls.
    scope = {'queue':params.get('queue','all'), 'q':params.get('q','')}
    if scope['queue'] == 'instruction':
        scope['q'] = ''
    with grid.selected_query(conn, user, scope) as (_, source, values, _order, today, soon):
        def register_url(**filters):
            return '/documents?' + urlencode({**scope, 'interactive':'1', **filters})
        workflow_counts = {row['key']:row['count'] for row in rows(conn,
            source.format(columns='d.status AS key,COUNT(*) AS count') + ' GROUP BY d.status', values)}
        workflow = [{'key':status, 'label':status.replace('_',' '), 'count':workflow_counts.pop(status,0),
                     'href':register_url(status=status)} for status in grid.STATUSES]
        # Keep unexpected legacy states visible in the total without inventing a valid filter.
        workflow += [{'key':key, 'label':str(key or 'Unknown workflow'), 'count':count, 'href':None}
                     for key,count in sorted(workflow_counts.items(), key=lambda pair:str(pair[0]))]
        conn.create_function('dashboard_deadline', 2,
            lambda status,due: grid.deadline_state(status,due,today,soon), deterministic=True)
        deadline_counts = {row['key']:row['count'] for row in rows(conn,
            source.format(columns='dashboard_deadline(d.status,d.due_date) AS key,COUNT(*) AS count') +
            ' GROUP BY dashboard_deadline(d.status,d.due_date)', values)}
        # Combine today with the next three working days, exactly matching due_soon in the grid.
        deadline_counts['due_soon'] = deadline_counts.get('due_soon',0) + deadline_counts.get('due_today',0)
        deadlines = [{'key':key,'label':label,'count':deadline_counts.get(key,0),'href':register_url(deadline=key)}
                     for key,label in DEADLINES]
        leads = rows(conn, source.format(columns=grid.group_projection('lead') + ',COUNT(*) AS count') +
                     ' GROUP BY COALESCE(u.id,0) ORDER BY count DESC,' + grid.GROUP_ORDERS['lead'] +
                     (' LIMIT :presentation_limit' if presentation else ''),
                     {**values,'presentation_limit':MAX_PRESENTATION_LEADS+1})
        if presentation and len(leads)>MAX_PRESENTATION_LEADS:
            raise ValueError('Narrow the dashboard queue or search to at most 1,000 lead groups before exporting this report.')
        leads = [{'key':row['group_key'], 'label':row['group_label'], 'count':row['count'],
                  'href':register_url(lead_id='unresolved' if row['group_key']=='0' else row['group_key'])}
                 for row in leads]
        return {'scope':scope, 'queue_label':dict(QUEUE_LABELS)[scope['queue']], 'total':sum(row['count'] for row in workflow),
                'workflow':workflow, 'deadlines':deadlines, 'leads':leads,
                'today':today.isoformat(), 'soon':soon.isoformat(), 'as_of':tz.now_iso(),
                'register_url':register_url(), 'pdf_url':'/documents/dashboard/export.pdf?'+urlencode(scope), 'chart_lead_limit':20}
