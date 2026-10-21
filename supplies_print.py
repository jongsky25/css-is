"""Authorized immutable submitted request/release data for A4 print views."""
import supplies as s
import supplies_requests as requests
import supplies_issues as issues
import supplies_stock as stock
from supplies_acknowledgments import _state
from supplies_storage import Conflict, rows


def request_print(conn,user,request_id,*,revision=None):
    with stock._snapshot(conn):
        current=requests.get_request(conn,user,request_id)
        version=current['current_revision'] if revision is None else s.integer(revision,'Submitted revision',1)
        found=rows(conn,'SELECT * FROM supply_request_revision WHERE request_id=? AND revision=?',(current['id'],version))
        if not found:
            raise Conflict('Only a saved submitted revision can be printed.')
        header=found[0]
        header['control_number']=current['control_number']
        lines=rows(conn,'''SELECT l.*,d.approved_quantity,d.reason AS reduction_reason,
          COALESCE(r.effective_issued_quantity,0) AS effective_issued_quantity,
          COALESCE(r.cancelled_quantity,0) AS cancelled_quantity,COALESCE(r.reserved_quantity,0) AS reserved_quantity,
          COALESCE(d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity-r.reserved_quantity,0) AS awaiting_stock_quantity
          FROM supply_request_revision_line l LEFT JOIN supply_request_decision_line d ON d.revision_line_id=l.id
          LEFT JOIN supply_reservation r ON r.revision_line_id=l.id WHERE l.revision_id=? ORDER BY l.line_id''',(header['id'],))
        releases=rows(conn,'SELECT * FROM supply_issue WHERE request_id=? AND submitted_revision=? ORDER BY id',(current['id'],version))
        for release in releases:
            release['lines']=rows(conn,'SELECT * FROM supply_issue_line WHERE issue_id=? ORDER BY id',(release['id'],))
            release['acknowledgment']=_state(conn,release['id'])
        decision=rows(conn,'SELECT * FROM supply_request_decision WHERE revision_id=?',(header['id'],))
        return {'print_kind':'request','header':header,'lines':lines,'releases':releases,
                'decision':decision[0] if decision else None,
                'quantity_label':'Requested quantity','date_issued':releases[0]['effective_date'] if len(releases)==1 else None,
                'multiple_releases':len(releases)>1,'issuer':releases[0]['issuer_snapshot'] if len(releases)==1 else ''}


def release_print(conn,user,issue_id):
    with stock._snapshot(conn):
        release=issues.get_issue(conn,user,issue_id)
        header=rows(conn,'SELECT * FROM supply_request_revision WHERE request_id=? AND revision=?',
                    (release['request_id'],release['submitted_revision']))[0]
        header['control_number']=release['request']['control_number']
        # Recipient access remains confined to this release and its submitted context.
        lines=rows(conn,'''SELECT i.*,l.requested_quantity,d.approved_quantity,d.reason AS reduction_reason
          FROM supply_issue_line i JOIN supply_request_revision_line l ON l.id=i.revision_line_id
          JOIN supply_request_decision_line d ON d.revision_line_id=l.id WHERE i.issue_id=? ORDER BY i.id''',(release['id'],))
        return {'print_kind':'release','header':header,'lines':lines,'releases':[release],
                'quantity_label':'Issued quantity','date_issued':release['effective_date'],
                'multiple_releases':False,'issuer':release['issuer_snapshot'],'decision':None}
