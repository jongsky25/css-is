"""Human-confirmed calendar links. Document content never enters calendar audiences."""
from datetime import date, timedelta
import storage as st
import office_calendar as oc
import documents as d
import documents_permissions as p
from documents_storage import rows, transaction
import tzutil as tz


def candidates(conn,user,doc_id,day):
    d.get(conn,user,doc_id)
    when=date.fromisoformat(day)
    return oc.items_between(conn,user,when-timedelta(days=7),when+timedelta(days=7),scope='blend',layers=['entries','activities'])


def confirm(conn,user,doc_id,revision,day,entry_id=None):
    with transaction(conn):
        user,doc=d.check(conn,user,doc_id,revision)
        d.require(p.can_work(conn,user,doc))
        date.fromisoformat(day)
        old=conn.execute('SELECT entry_id FROM document_calendar WHERE document_id=?',(doc_id,)).fetchone()
        if old:
            raise d.Conflict('A calendar entry is already linked. Reschedule it explicitly in Calendar.')
        if entry_id:
            candidate=st.cal_get(conn,int(entry_id))
            ctx=oc.viewer_context(conn,user)
            unit=conn.execute('SELECT path FROM org_unit WHERE id=?',(candidate['owner_org_id'],)).fetchone() if candidate else None
            d.require(candidate and oc.entry_visible(ctx,candidate,unit[0] if unit else None))
        else:
            # A generic private reminder deliberately contains no document title,
            # number, source URL or sender, even if app access is later revoked.
            entry_id=st.cal_create(conn,'Document follow-up',day,audience='people',people=[(user['id'],'attending')],
                                   by=user['username'],audit_it=False,commit=False)
        conn.execute('INSERT INTO document_calendar VALUES (?,?,?,?)',(doc_id,entry_id,user['id'],tz.now_iso()))
        return d.finish(conn,user,doc,'calendar_confirmed',{'entry_id':entry_id,'day':day})
