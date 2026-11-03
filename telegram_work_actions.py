"""Shared current-work rules for narrow private task actions."""
import hashlib
import json

from documents_storage import rows
import telegram_actions as actions
import work
import work_compat


def require_work(conn,user,case_id):
    work.writable(conn)
    item=work.get(conn,user,case_id)
    work_compat.require_open(conn,item['id'])
    if conn.execute('''SELECT 1 FROM work_review_packet p JOIN document d ON d.id=p.document_id
        WHERE p.case_id=? AND d.status NOT IN ('closed','cancelled','released','awaiting_acknowledgment')
        AND NOT EXISTS(SELECT 1 FROM work_review_packet newer WHERE newer.document_id=p.document_id AND newer.id>p.id)
        AND NOT EXISTS(SELECT 1 FROM work_review_invalidation i WHERE i.packet_id=p.id) LIMIT 1''',(item['id'],)).fetchone():
        raise actions.Unavailable('Amend work under active consolidation review in Office Connect so dependent approvals can be reviewed there.')
    return item


def source_state(conn,item,task=None):
    documents=[]
    for link in rows(conn,'SELECT * FROM work_document WHERE case_id=? ORDER BY document_id',(item['id'],)):
        doc=work.resolved_document(conn,link['document_id'])
        documents.append([link,{k:doc[k] for k in ('id','canonical_id','revision','due_date','status')} if doc else None])
    # Source contents are hashed only, never projected or stored in descriptors.
    # json.dumps allows normal long source submissions without imposing a reply-size limit.
    digest=hashlib.sha256(json.dumps([item,documents,task],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'source':digest,'event_id':conn.execute('SELECT COALESCE(MAX(id),0) FROM work_event WHERE case_id=?',(item['id'],)).fetchone()[0]}
