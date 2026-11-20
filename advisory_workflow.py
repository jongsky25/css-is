"""Private, versioned activity advisories using Documents identity and audit history."""
import hashlib
import json
import re
import uuid

import activity_advisory as aa
import activity_permissions
import advisory
import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction, event
import storage as st
import tzutil as tz
import work

MAX_ARTIFACT_BYTES = 5 * 1024 * 1024


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def for_event(conn, event_id):
    found = rows(conn, 'SELECT * FROM advisory_record WHERE event_id=?', (event_id,))
    return found[0] if found else None


def for_document(conn, document_id):
    found = rows(conn, 'SELECT * FROM advisory_record WHERE document_id=?', (document_id,))
    return found[0] if found else None


def require_unmanaged(conn, document_id):
    if for_document(conn, document_id):
        raise ValueError('Open the advisory draft. Review, approval and issuance are not available yet.')


def available(conn):
    return docs.enabled(conn) and work.enabled(conn)


def divisions(conn):
    return rows(conn, "SELECT id,name FROM org_unit WHERE level='division' ORDER BY name,id")


def source(conn, ev):
    # Activity facts only, excluding global last-used contact defaults.
    return {'activity': {k: ev.get(k) for k in ('id','title','event_date','end_date','venue','modality','event_kind')},
            'links': [(r['label'],r['url']) for r in st.list_event_links(conn,ev['id']) if not r['visible_after_done']],
            'window': st.get_event_window(conn,ev['id']) or {},
            'has_registration': bool(st.get_event_forms(conn,ev['id']))}


def source_hash(conn, ev):
    return digest(encoded(source(conn,ev)))


def get_visible(conn, user, advisory_id):
    user = permissions.actor(conn,user)
    found = rows(conn, '''SELECT a.*,d.revision,d.status,d.archived_at,e.event_token,e.title AS activity_title
        FROM advisory_record a JOIN document d ON d.id=a.document_id
        LEFT JOIN event e ON e.id=a.event_id WHERE a.id=?''', (advisory_id,))
    if not found:
        raise permissions.Denied('Advisory not found or unavailable to you.')
    record = found[0]
    docs.get(conn,user,record['document_id'])
    revision = rows(conn,'SELECT * FROM advisory_revision WHERE id=? AND advisory_id=?',
                    (record['current_revision'],record['id']))[0]
    return dict(record, payload=json.loads(revision['payload_json']), snapshot=json.loads(revision['source_json']),
                ordinal=revision['ordinal'])


def list_visible(conn, user, *, before=0, unit_id=0, limit=30):
    user = permissions.actor(conn,user)
    scope = permissions.RegistryScope(conn,user)
    params = {**scope.params,'before':before,'unit':unit_id,'limit':limit+1}
    where = f'''FROM advisory_record a JOIN document d ON d.id=a.document_id
        JOIN event e ON e.id=a.event_id JOIN org_unit u ON u.id=a.unit_id
        WHERE {scope.view_sql('d')} AND (:before=0 OR a.id<:before) AND (:unit=0 OR a.unit_id=:unit)'''
    found = rows(conn, '''SELECT a.id,a.number,a.unit_id,d.subject,d.status,e.event_token,u.name AS division
        ''' + where + ' ORDER BY a.id DESC LIMIT :limit', params)
    total = conn.execute('SELECT COUNT(*) ' + where, {**params,'before':0}).fetchone()[0]
    return {'items':found[:limit], 'total':total, 'older':found[limit-1]['id'] if len(found)>limit else None}


def list_existing(conn,user,before=0):
    """Read-only compatibility projection; no invented division or approval history."""
    user=permissions.actor(conn,user)
    result=[]
    cursor=conn.execute('''SELECT a.event_id,a.number,a.headline,a.published,e.event_token FROM event_advisory a
        JOIN event e ON e.id=a.event_id LEFT JOIN advisory_record managed ON managed.event_id=a.event_id
        WHERE managed.id IS NULL AND (?=0 OR a.event_id<?) ORDER BY a.event_id DESC''',(before,before))
    names=[column[0] for column in cursor.description]
    for values in cursor:
        row=dict(zip(names,values))
        ev=st.get_event(conn,row['event_token'])
        if activity_permissions.can_manage(user,ev,conn):
            result.append(row)
            if len(result)==31:break
    return {'items':result[:30],'older':result[29]['event_id'] if len(result)>30 else None}


def history(conn, user, advisory_id, before=0):
    get_visible(conn,user,advisory_id)
    return rows(conn, '''SELECT r.id,r.ordinal,r.created_at,r.summary,r.payload_json,u.username AS author,
        (SELECT p.payload_json FROM advisory_revision p WHERE p.advisory_id=r.advisory_id AND p.ordinal<r.ordinal
         ORDER BY p.ordinal DESC LIMIT 1) AS previous_payload
        FROM advisory_revision r JOIN admin_user u ON u.id=r.actor_id
        WHERE r.advisory_id=? AND (?=0 OR r.id<?) ORDER BY r.ordinal DESC LIMIT 31''',
        (advisory_id,before,before))


def artifact(conn, user, advisory_id, revision_id, fmt):
    get_visible(conn,user,advisory_id)
    found = rows(conn, '''SELECT f.data,f.sha256 FROM advisory_artifact f JOIN advisory_revision r ON r.id=f.revision_id
        WHERE r.advisory_id=? AND r.id=? AND f.format=?''',(advisory_id,revision_id,fmt))
    if not found or digest(found[0]['data']) != found[0]['sha256']:
        raise ValueError('This saved artifact is unavailable.')
    return found[0]['data']


def existing_public(conn, event_id, fmt):
    found = rows(conn, '''SELECT p.data,p.sha256 FROM advisory_existing_public p
        JOIN advisory_record a ON a.id=p.advisory_id WHERE a.event_id=? AND p.format=?''',(event_id,fmt))
    if not found or digest(found[0]['data']) != found[0]['sha256']:
        raise ValueError('This advisory is not available.')
    return found[0]['data']


def normalized(fields, unit_id, audience, external):
    if audience not in ('internal','external','both'):
        raise ValueError('Choose internal, external, or both audiences.')
    if len(external)>64000:
        raise ValueError('Use at most 500 external addresses.')
    addresses = sorted(set(x.strip().casefold() for x in re.split(r'[,;\s]+',external) if x.strip()))
    if len(addresses)>500 or any(len(a)>254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',a) for a in addresses):
        raise ValueError('Enter valid external email addresses, up to 500 per advisory.')
    if audience=='internal' and addresses:
        raise ValueError('Choose both audiences to include external recipients, or clear their addresses.')
    if audience in ('external','both') and not addresses:
        raise ValueError('Add at least one external email address.')
    clean = advisory.normalise(aa.poster_fields(fields,''))
    content = {k:clean[k] for k in ('headline','attention','body','rows','qr_url')+aa.CONTACT}
    if not content['headline'] or not content['contact_name']:
        raise ValueError('Add a headline and a contact person.')
    return {'content':content,'unit_id':int(unit_id),'audience':audience,'external':addresses}


def _render(fields, number):
    poster = aa.poster_fields(fields,number)
    result = {'pdf':advisory.render_pdf(poster),'png':advisory.render_png(poster)}
    if any(len(data)>MAX_ARTIFACT_BYTES for data in result.values()):
        raise ValueError('The advisory is too large. Shorten its contents and try again.')
    return result


def save_draft(conn, user, event_token, fields, *, unit_id, audience, external, expected_revision,
               expected_source, operation_key, summary='', adopt_source=False, expected_legacy_revision=0):
    """One quiet transaction. No network or implicit feature activation."""
    user = permissions.actor(conn,user)
    docs.writable(conn); work.writable(conn)
    try:
        operation_key = str(uuid.UUID(operation_key))
        expected_revision = int(expected_revision)
        expected_legacy_revision = int(expected_legacy_revision)
        unit_id = int(unit_id)
    except (ValueError,TypeError,AttributeError):
        raise ValueError('Reload the form before saving this draft.') from None
    if len(summary)>2000:
        raise ValueError('Keep the change summary within 2000 characters.')
    payload = normalized(fields,unit_id,audience,external)
    request_hash = digest(encoded([event_token,payload,summary.strip(),expected_revision,expected_source,
                                   adopt_source,expected_legacy_revision]))
    with transaction(conn):
        user = permissions.actor(conn,user)
        docs.writable(conn); work.writable(conn)
        ev = st.get_event(conn,event_token)
        if not ev:
            raise permissions.Denied('Activity not found or unavailable to you.')
        record = for_event(conn,ev['id'])
        if record:
            current = get_visible(conn,user,record['id'])
            if record['initiator_id']!=user['id']:
                raise permissions.Denied('Only the initiator may edit this draft.')
        elif not activity_permissions.can_manage(user,ev,conn):
            raise permissions.Denied('You cannot prepare this activity advisory.')
        replay = rows(conn,'SELECT * FROM advisory_save_request WHERE actor_id=? AND operation_key=?',(user['id'],operation_key))
        if replay:
            if replay[0]['payload_hash']!=request_hash or replay[0]['event_id']!=ev['id']:
                raise docs.Conflict('This save request was already used for different contents. Reload the form.')
            return get_visible(conn,user,replay[0]['advisory_id'])
        if st.event_is_archived(conn,ev['id']):
            raise ValueError('Restore the activity before editing its advisory.')
        if record and (current['revision']!=expected_revision or current['status'] not in ('draft','changes_requested') or current['archived_at']):
            raise docs.Conflict('The advisory changed. Open the latest draft before saving again; your entered values are shown below.')
        if not record and expected_revision!=0:
            raise docs.Conflict('The advisory changed. Reload before saving.')
        if not conn.execute("SELECT 1 FROM org_unit WHERE id=? AND level='division'",(unit_id,)).fetchone():
            raise ValueError('Choose an owning division.')
        source_value = source(conn,ev)
        if digest(encoded(source_value))!=expected_source:
            raise docs.Conflict('Activity details changed. Reload and compare them before saving; your entered values are shown below.')
        if record and not adopt_source:
            source_value = current['snapshot']
        payload_json = encoded(payload)
        payload_hash = digest(encoded([payload,source_value]))
        prior = rows(conn,'SELECT * FROM advisory_revision WHERE id=?',(record['current_revision'],))[0] if record else None
        if prior and prior['payload_hash']==payload_hash:
            rid = prior['id']; aid = record['id']
        else:
            if prior and not summary.strip():
                raise ValueError('Describe the changes for the revision history.')
            now = tz.now_iso()
            if not record:
                legacy = aa.get(conn,ev['id'])
                if (legacy or {}).get('revision',0)!=expected_legacy_revision:
                    raise docs.Conflict('The existing advisory changed. Reload before preparing its private draft.')
                frozen = _render(legacy,legacy['number']) if legacy and legacy['published'] else {}
                # Reserve once through the original numbering service; existing fields stay intact.
                if not legacy:
                    legacy = aa.save_in_transaction(conn,ev,payload['content'],user,remember_contact=False)
                doc = docs.register_in_transaction(conn,user,{'direction':'OUT','subject':payload['content']['headline'],
                    'type':'advisory','unit_id':unit_id},suppress_assignments=True,defer_rules=True,quiet=True)
                conn.execute("UPDATE document SET visibility='restricted',policy_json=? WHERE id=?",
                             (encoded({'workflow':'advisory_draft'}),doc['id']))
                conn.execute('INSERT INTO document_access VALUES (?,?,?)',(doc['id'],user['id'],'advisory_initiator'))
                aid = conn.execute('''INSERT INTO advisory_record(document_id,event_id,number,reservation_date,initiator_id,unit_id,created_at)
                    VALUES (?,?,?,?,?,?,?)''',(doc['id'],ev['id'],legacy['number'],legacy['seq_date'],user['id'],unit_id,now)).lastrowid
                for fmt,data in frozen.items():
                    conn.execute('INSERT INTO advisory_existing_public VALUES (?,?,?,?,?)',(aid,fmt,data,digest(data),now))
                record = for_event(conn,ev['id'])
                ordinal = 1
            else:
                doc = docs.raw(conn,record['document_id']); aid = record['id']; ordinal = prior['ordinal']+1
            rendered = _render(payload['content'],record['number'])
            # The local authenticated URL is real; an empty file_id explicitly is not a Drive ID.
            rid = conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM advisory_revision').fetchone()[0]
            vid = conn.execute('''INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,parent_id,actor_id,created_at,backend)
                VALUES (?,?,'',?,'draft',?,?,?,'advisory')''',(doc['id'],f'/advisories/{aid}/revisions/{rid}/file.pdf',digest(rendered['pdf']),
                doc['current_version'],user['id'],now)).lastrowid
            conn.execute('''INSERT INTO advisory_revision(id,advisory_id,ordinal,version_id,payload_json,payload_hash,source_json,actor_id,created_at,summary)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',(rid,aid,ordinal,vid,payload_json,payload_hash,encoded(source_value),user['id'],now,
                summary.strip() or 'Initial private draft'))
            for fmt,data in rendered.items():
                conn.execute('INSERT INTO advisory_artifact VALUES (?,?,?,?)',(rid,fmt,digest(data),data))
            conn.execute('UPDATE advisory_record SET current_revision=?,unit_id=? WHERE id=?',(rid,unit_id,aid))
            conn.execute('''UPDATE document SET current_version=?,revision=?,subject=?,unit_id=?,updated_at=?,status='draft',approved_version=NULL,signed_version=NULL WHERE id=?''',
                         (vid,doc['revision']+1 if prior else 1,payload['content']['headline'],unit_id,now,doc['id']))
            if record.get('case_id'):
                conn.execute('UPDATE work_case SET unit_id=?,revision=revision+1,updated_at=? WHERE id=?',(unit_id,now,record['case_id']))
            if prior and record['unit_id']!=unit_id:
                conn.execute("DELETE FROM document_access WHERE document_id=? AND source='advisory_routing'",(doc['id'],))
            event(conn,doc['id'],user,'advisory_draft_saved',{'advisory_id':aid,'revision_id':rid,'ordinal':ordinal,'summary':summary.strip()})
        conn.execute('INSERT INTO advisory_save_request VALUES (?,?,?,?,?,?)',(user['id'],operation_key,ev['id'],request_hash,aid,rid))
        return get_visible(conn,user,aid)
