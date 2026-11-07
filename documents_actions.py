"""Paged, permission-filtered document steps using the detail workflow guidance."""
from datetime import date
import json

import documents as docs
import documents_guidance as guidance
import documents_permissions as permissions
import documents_registry as registry
from documents_storage import rows
import tzutil
import work_review

PAGE_SIZE=30
MAX_PAGE_SIZE=50
CHILD_LIMIT=3
SCAN_BATCH=1024
STATES=('all','ready','waiting','attention')
LIVE="d.archived_at IS NULL AND d.canonical_id IS NULL AND d.status NOT IN ('closed','cancelled')"


def _date_label(due,today):
    if not due:return 'Deadline unknown'
    if due<today:return 'Overdue · '+due
    if due==today:return 'Due today · '+due
    return 'Due '+due


def _card(doc,kind,action,due,today,url,detail='',*,state='ready',owner=None,role='',blocker=None,cta=None,identity='workflow',summary=False):
    if summary:
        return {'document_id':doc['id'],'state':state,'overdue':bool(due and due<today)}
    return {'anchor':f"document-step-{doc['id']}-{identity}",'document_id':doc['id'],'number':doc['number'],'subject':doc['subject'],
            'kind':kind,'action':action,'detail':detail,'due':due,
            'due_label':_date_label(due,today),'url':url,'overdue':bool(due and due<today),
            'state':state,'state_label':{'ready':'Ready for you','waiting':'Waiting','attention':'Needs attention'}[state],
            'owner_id':owner,'owner_role':role,'blocker':blocker,'cta':cta}


def _selection(scope,view):
    uid=':registry_actor'
    own=f"""EXISTS(SELECT 1 FROM document_assignment a WHERE a.document_id=d.id
        AND a.user_id={uid} AND a.status IN ('assigned','acknowledged','in_progress')
        AND NOT EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=d.id))"""
    if view=='division':
        return f"""d.unit_id IN (SELECT value FROM json_each(:registry_division_units)) AND (
            d.lead_id IS NULL OR d.reconcile OR (d.due_date IS NOT NULL AND d.due_date<:action_today)
            OR EXISTS(SELECT 1 FROM document_assignment_effective a WHERE a.document_id=d.id AND (
                a.status IN ('proposed','assigned','submitted') OR
                (a.status NOT IN ('completed','superseded') AND a.due_date<:action_today))))"""
    return f"""(d.lead_id={uid} OR d.reviewer_id={uid} OR {own}
        OR (d.creator_id={uid} AND (d.direction='OUT' OR d.verification='needs_correction'))
        OR (:action_director=1 AND d.instruction_state='pending')
        OR ({scope.officer_sql('d')} AND (d.verification<>'verified' OR d.lead_id IS NULL OR
            EXISTS(SELECT 1 FROM document_assignment a WHERE a.document_id=d.id AND a.status='submitted'
              AND NOT EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=d.id)) OR
            (d.direction='OUT' AND d.status IN ('approved','ready_to_release'))))
        OR ({scope.signatory_sql('d')} AND d.status='approved' AND d.signed_version IS NOT d.current_version)
        OR EXISTS(SELECT 1 FROM document_job j WHERE j.document_id=d.id AND j.actor_id={uid}
            AND j.kind IN ('sign','dispatch') AND j.state IN ('pending','running','unknown'))
        OR EXISTS(SELECT 1 FROM document_instruction_recipient r JOIN document_directive x ON x.id=r.directive_id
            LEFT JOIN document_instruction_read seen ON seen.directive_id=x.id AND seen.user_id=r.user_id
            WHERE x.document_id=d.id AND r.user_id={uid} AND seen.directive_id IS NULL
              AND EXISTS(SELECT 1 FROM document_instruction_tag t WHERE t.directive_id=x.id)))"""


def _page_records(conn,scope,view,today,before,due,limit,*,scan=False):
    # Seek on the complete deadline/ID order. Authority and scope precede LIMIT.
    params={**scope.params,'action_today':today,'action_director':int(scope.is_director),
            'action_before':before,'action_due':due,'action_limit':-1 if scan else limit+1}
    assignment_table='document_assignment_effective' if view=='division' else 'document_assignment'
    due_filter=("a.status NOT IN ('completed','superseded')" if view=='division' else
        f"""((a.user_id=:registry_actor AND a.status IN ('assigned','acknowledged','in_progress'))
          OR (a.status='submitted' AND (d.lead_id=:registry_actor OR {scope.officer_sql('d')})))
          AND NOT EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=d.id)""")
    projection=("d.id,d.direction,d.status,d.verification,d.archived_at,d.lead_id,d.creator_id,"
                "d.reviewer_id,d.review_class,d.unit_id,d.matches_json,d.canonical_id,d.visibility,"
                "d.instruction_state,d.reconcile,d.due_date,d.policy_json,"
                "d.current_version,d.approved_version,d.signed_version,'' AS number,'' AS subject" if scan else 'd.*')
    sql=f"""WITH {scope.assignment_ctes()}, action_candidates AS (
        SELECT d.id,MIN(COALESCE(NULLIF(d.due_date,''),'9999-12-31'),COALESCE((
            SELECT MIN(NULLIF(a.due_date,'')) FROM {assignment_table} a WHERE a.document_id=d.id
              AND {due_filter}), '9999-12-31')) AS sort_due
        FROM document d WHERE {LIVE} AND {scope.view_sql('d')} AND ({_selection(scope,view)})
    ), action_page AS MATERIALIZED (
        SELECT * FROM action_candidates WHERE :action_before=0 OR sort_due>:action_due
          OR (sort_due=:action_due AND id<:action_before)
        ORDER BY sort_due,id DESC LIMIT :action_limit)
    SELECT {projection},page.sort_due,{scope.officer_sql('d')} AS action_officer,
        {scope.work_sql('d')} AS action_can_work,{scope.release_sql('d')} AS action_can_release,
        {scope.workflow_sql('d')} AS action_can_archive,{scope.signatory_sql('d')} AS action_signatory,
        {docs.closure_facts_sql('d')},
        EXISTS(SELECT 1 FROM document_job j WHERE j.document_id=d.id AND j.actor_id=:registry_actor
          AND j.kind IN ('sign','dispatch') AND j.state IN ('pending','running','unknown')) AS action_own_operation,
        EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=d.id) AS action_migrated,
        EXISTS(SELECT 1 FROM work_review_packet p WHERE p.document_id=d.id) AS action_packet,
        (EXISTS(SELECT 1 FROM work_review_packet p WHERE p.document_id=d.id)
          OR EXISTS(SELECT 1 FROM work_completion_requirement r WHERE r.document_id=d.id)
          OR EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=d.id)) AS action_release_check,
        EXISTS(SELECT 1 FROM document_dispatch_recipient r JOIN document_dispatch x ON x.id=r.dispatch_id
          WHERE x.document_id=d.id AND x.version_id=d.current_version) AS action_delivery,
        EXISTS(SELECT 1 FROM document_dispatch_recipient r JOIN document_dispatch x ON x.id=r.dispatch_id
          WHERE x.document_id=d.id AND x.version_id=d.current_version AND r.outcome='unknown') AS action_unknown
    FROM action_page page JOIN document d ON d.id=page.id ORDER BY page.sort_due,d.id DESC"""
    if scan:
        return conn.execute(sql,params)
    return rows(conn,sql,params)


def _group(records):
    result={}
    for record in records:result.setdefault(record['document_id'],[]).append(record)
    return result


def _load(conn,scope,documents,*,summary=False,overdue=False,today=None):
    """Batch ordinary page data; never load histories, files or all task bodies."""
    params={**scope.params,'action_ids':json.dumps([d['id'] for d in documents]),'child_limit':1 if summary else CHILD_LIMIT,
            'action_overdue':int(overdue),'action_today':today}
    ids='SELECT value FROM json_each(:action_ids)'
    assignments=_group(rows(conn,f"""WITH numbered AS (
        SELECT a.id,a.document_id,a.user_id,a.status,a.due_date,'' AS action,ROW_NUMBER() OVER (PARTITION BY a.document_id ORDER BY COALESCE(NULLIF(a.due_date,''),NULLIF(d.due_date,''),'9999-12-31'),a.id) AS position
        FROM document_assignment a JOIN document d ON d.id=a.document_id
        WHERE a.document_id IN ({ids})
          AND (:action_overdue=0 OR COALESCE(NULLIF(a.due_date,''),d.due_date)<:action_today) AND NOT EXISTS(
          SELECT 1 FROM work_legacy_document m WHERE m.document_id=a.document_id)
          AND ((a.user_id=:registry_actor AND a.status IN ('assigned','acknowledged','in_progress')) OR
          (a.status='submitted' AND (d.lead_id=:registry_actor OR {scope.officer_sql('d')}))))
        SELECT * FROM numbered WHERE position<=:child_limit""",params))
    instructions=_group(rows(conn,f"""WITH numbered AS (
        SELECT x.id,x.document_id,'' AS text,
          ROW_NUMBER() OVER (PARTITION BY x.document_id ORDER BY x.id DESC) AS position
        FROM document_directive x JOIN document_instruction_recipient r ON r.directive_id=x.id
        LEFT JOIN document_instruction_read seen ON seen.directive_id=x.id AND seen.user_id=r.user_id
        WHERE x.document_id IN ({ids}) AND r.user_id=:registry_actor AND seen.directive_id IS NULL
          AND (:action_overdue=0 OR x.document_id IN (SELECT id FROM document WHERE due_date<:action_today))
          AND EXISTS(SELECT 1 FROM document_instruction_tag t WHERE t.directive_id=x.id))
        SELECT * FROM numbered WHERE position<=:child_limit""",params))
    versions=_group(rows(conn,f"""SELECT v.id,v.document_id,v.fingerprint FROM document_file_version v
        JOIN document d ON d.current_version=v.id AND d.id=v.document_id WHERE d.id IN ({ids})""",params))
    jobs=_group(rows(conn,f"""WITH numbered AS (
        SELECT j.id,j.document_id,j.actor_id,j.kind,j.state,
          ROW_NUMBER() OVER (PARTITION BY j.document_id ORDER BY j.id DESC) AS position
        FROM document_job j WHERE j.document_id IN ({ids}) AND j.kind IN ('sign','dispatch')
          AND j.state IN ('pending','running','unknown')) SELECT * FROM numbered WHERE position=1""",params))
    # The registry's shared SQL authority is the counterpart of work._can_view.
    # Guidance needs only the newest permitted case ID, never case/task bodies.
    # Every linked source (including aliases) must remain readable.
    cases=_group(rows(conn,f"""WITH RECURSIVE aliases(document_id,id) AS (
        SELECT id,id FROM document WHERE id IN ({ids}) UNION
        SELECT a.document_id,d.id FROM document d JOIN aliases a ON d.canonical_id=a.id)
        SELECT a.document_id,MAX(w.id) AS id FROM aliases a
        JOIN work_document link ON link.document_id=a.id JOIN work_case w ON w.id=link.case_id
        WHERE {scope.work_view_sql('w')} GROUP BY a.document_id""",params))
    return assignments,instructions,versions,jobs,cases


class _GuidanceValues(dict):
    """Load strict shared-work facts only if the guidance branch needs them."""
    def __init__(self,values,loaders):
        super().__init__(values)
        self.loaders=loaders

    def __missing__(self,key):
        value=self.loaders.pop(key)()
        self[key]=value
        return value


def _cards(conn,scope,documents,today,view,*,summary=False,overdue=False):
    # All eligible contributions share the document's paused/ready state, and all
    # unread instructions share its enabled state. For DOCUMENT counts a single
    # earliest-due contribution and an instruction represent each whole set,
    # including overdue membership; this is not a total of individual steps.
    assignments,instructions,versions,jobs,cases=_load(
        conn,scope,documents,summary=summary,overdue=overdue,today=today)
    user=scope.user;uid=user['id'];enabled=docs.enabled(conn);cards=[]
    for doc in documents:
        did=doc['id'];base=f'/documents/{did}'
        own=assignments.get(did,[])
        for a in own:a['progress_choices']=guidance.assignment_choices(user,doc,doc['action_officer'],a)
        values=_GuidanceValues({'doc':doc,'policy':json.loads(doc['policy_json']),
            'officer':doc['action_officer'],'can_work':doc['action_can_work'],
            'can_release':doc['action_can_release'],'can_archive':doc['action_can_archive'],
            'signatory':doc['action_signatory'],'assignments':own,
            'assignments_migrated':doc['action_migrated'],
            'versions':versions.get(did,[]),'jobs':jobs.get(did,[]),
            'prepared':{'enabled':enabled,'director':scope.is_director,'closure_facts':doc,
                'packet_exists':doc['action_packet'],'release_clear':not doc['action_release_check'],
                'delivery_state':'unknown' if doc['action_unknown'] else 'partial' if doc['action_delivery'] else 'none'}},
            {'work_cases':lambda: cases.get(did,[]),
             'consolidation':lambda: work_review.summaries(conn,user,[doc]).get(did) if doc['action_packet'] else None})
        advice=guidance.build(conn,user,values)
        step=advice['stage']
        if view=='mine':
            for note in instructions.get(did,[]):
                cards.append(_card(doc,'Instruction','Read and acknowledge instruction',doc['due_date'],today,
                    base+f"#instruction-{note['id']}",note['text'],owner=uid,role='Instruction recipient',
                    state='ready' if enabled else 'waiting',blocker=None if enabled else advice['message'],cta='Read instruction',identity=f"instruction-{note['id']}",summary=summary))
            for a in own:
                if not a['progress_choices']:continue
                paused=not enabled or doc['instruction_state']=='pending' or bool(jobs.get(did))
                card_url=base+'#document-next' if paused else base+f"#document-contribution-{a['id']}"
                cards.append(_card(doc,'Contribution',a['progress_choices'][0][1],a['due_date'] or doc['due_date'],today,
                    card_url,a['action'],state='waiting' if paused else 'ready',
                    owner=advice['owner_id'] if paused else uid,
                    role=advice['owner_role'] if paused else 'Contributor' if a['status']!='submitted' else 'Lead or records officer',
                    blocker=advice['message'] if paused else None,cta='View next step' if paused else 'Update contribution',identity=f"contribution-{a['id']}",summary=summary))
            # A contributor-only reader keeps concrete personal steps, rather
            # than acquiring a new lead/reviewer task by being able to view it.
            responsible=(doc['lead_id']==uid or doc['reviewer_id']==uid or doc['creator_id']==uid
                         or doc['action_officer'] or doc['action_signatory']
                         or doc['action_own_operation'])
            if not responsible:continue
        attention=step in ('operation','delivery_unknown','delivery_partial','consolidation','review_authority','closure_policy','release_policy')
        state='attention' if attention else 'ready' if advice['action'] else 'waiting'
        link=advice['action']
        url=(base+link['href'] if link and link['href'].startswith('#') else link['href'] if link else base+'#document-next')
        kind=('Division follow-up' if view=='division' else {'review':'Review','review_authority':'Review',
              'reconcile':'Reconciliation','instruction':'Director routing'}.get(step,'Lead follow-up'))
        action='Reconcile changed instruction or policy' if step=='reconcile' else advice['title']
        cards.append(_card(doc,kind,action,doc['due_date'],today,url,advice['message'],
            state=state,owner=advice['owner_id'],role=advice['owner_role'],blocker=advice['blocker'],
            cta=link['label'] if link else 'View next step',summary=summary))
    return cards


def _matches(card,state,overdue):
    return (state=='all' or card['state']==state) and (not overdue or card['overdue'])


def _display(conn,cards,state,overdue):
    """Filter before child caps, then fetch bodies only for displayed children."""
    selected=[];seen={}
    for card in cards:
        if not _matches(card,state,overdue):continue
        key=(card['document_id'],card['kind'])
        if card['kind'] in ('Instruction','Contribution'):
            if seen.get(key,0)>=CHILD_LIMIT:continue
            seen[key]=seen.get(key,0)+1
        selected.append(card)
    for kind,table,column in (('Instruction','document_directive','substr(text,1,240)'),
                              ('Contribution','document_assignment','action')):
        children=[c for c in selected if c['kind']==kind]
        if not children:continue
        ids=[int(c['anchor'].rsplit('-',1)[1]) for c in children]
        bodies=dict(conn.execute(f'SELECT id,{column} FROM {table} WHERE id IN (SELECT value FROM json_each(?))',
                                 (json.dumps(ids),)))
        for card,ident in zip(children,ids):card['detail']=bodies[ident]
    return selected


def _personal_page(conn,scope,today,before,before_due,limit,state,overdue):
    counts=dict.fromkeys(STATES,0);selected=[]
    cursor=_page_records(conn,scope,'mine',today,0,'',limit,scan=True)
    columns=[c[0] for c in cursor.description]
    try:
        while batch:=cursor.fetchmany(SCAN_BATCH):
            documents=[dict(zip(columns,row)) for row in batch]
            classified=_group(_cards(conn,scope,documents,today,'mine',summary=True))
            for doc in documents:
                states={c['state'] for c in classified.get(doc['id'],[]) if not overdue or c['overdue']}
                if not states:continue
                counts['all']+=1
                for value in states:counts[value]+=1
                after=not before or doc['sort_due']>before_due or (doc['sort_due']==before_due and doc['id']<before)
                if after and (state=='all' or state in states) and len(selected)<=limit:
                    selected.append(doc)
    finally:
        cursor.close()
    more=len(selected)>limit;documents=selected[:limit]
    if documents:
        labels={r['id']:r for r in rows(conn,'SELECT id,number,subject FROM document WHERE id IN (SELECT value FROM json_each(?))',
                                      (json.dumps([d['id'] for d in documents]),))}
        for doc in documents:doc.update(labels[doc['id']])
    cards=_display(conn,_cards(conn,scope,documents,today,'mine',overdue=overdue),state,overdue) if documents else []
    return documents,cards,more,counts


def page(conn,user,view='mine',*,today=None,before=0,before_due='',limit=PAGE_SIZE,step_state='all',overdue='0'):
    if view not in ('mine','division'):raise ValueError('Unknown action view.')
    if step_state not in STATES or overdue not in ('0','1'):
        raise ValueError('Invalid step filter. Reset My next steps and try again.')
    if view=='division' and (step_state!='all' or overdue!='0'):
        raise ValueError('Step filters are available on My next steps only.')
    before=registry.cursor(before)
    if before:
        try:before_due=date.fromisoformat(before_due).isoformat()
        except (ValueError,TypeError):raise ValueError('Invalid action page. Open the first page and try again.') from None
    elif before_due:raise ValueError('Invalid action page. Open the first page and try again.')
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=MAX_PAGE_SIZE:
        raise ValueError('Invalid action page size.')
    snapshot_at=tzutil.now_local().isoformat(timespec='seconds')
    today=str(today or snapshot_at[:10])
    with registry.snapshot(conn):
        scope=permissions.RegistryScope(conn,user)
        if view=='division' and not scope.division_units:
            raise permissions.Denied('Division follow-up is for division chiefs or OICs.')
        counts=None
        if view=='mine':
            documents,cards,more,counts=_personal_page(conn,scope,today,before,before_due,limit,step_state,overdue=='1')
        else:
            found=_page_records(conn,scope,view,today,before,before_due,limit)
            more=len(found)>limit;documents=found[:limit]
            cards=_display(conn,_cards(conn,scope,documents,today,view),'all',False) if documents else []
        return {'cards':cards,'document_count':len(documents),'more':more,'has_before':bool(before),
                'next_before':documents[-1]['id'] if more else None,
                'next_due':documents[-1]['sort_due'] if more else None,
                'division_access':bool(scope.division_units),'counts':counts,
                'step_state':step_state,'overdue':overdue,'snapshot_at':snapshot_at}


def personal(conn,user,today=None):
    return page(conn,user,today=today)['cards']


def division_units(conn,user):
    user=permissions.actor(conn,user)
    return [s['id'] for s in permissions.seats(conn,user) if s['level']=='division']


def team(conn,user,today=None):
    if not division_units(conn,user):return []
    return page(conn,user,'division',today=today)['cards']
