"""S5.2 numbered replenishment submissions, decisions and procurement tracking."""
import supplies as s
import supplies_permissions as permissions
import supplies_replenishment as rep
import supplies_stock as stock
import tzutil as tz
from supplies_storage import Conflict, Denied, Invalid, Missing, operation, record, rows, transaction


def _number(conn):
    year = tz.today_local().year
    conn.execute("INSERT INTO supply_sequence(kind,year,last_value) VALUES ('REP',?,0) ON CONFLICT(kind,year) DO NOTHING", (year,))
    last = conn.execute("SELECT last_value FROM supply_sequence WHERE kind='REP' AND year=?", (year,)).fetchone()[0]
    if last >= 99999:
        raise Conflict('The annual replenishment number limit has been reached.')
    conn.execute("UPDATE supply_sequence SET last_value=last_value+1 WHERE kind='REP' AND year=?", (year,))
    return f'REP-{year}-{last+1:05d}'


def _revision(request, expected_revision):
    if request['revision'] != s.integer(expected_revision, 'Replenishment revision', 1):
        raise Conflict('This replenishment changed. Reload it before continuing.')


def _overlap(conn, replenishment_id, item_id):
    return rows(conn, '''SELECT p.id,p.control_number,p.status FROM supply_replenishment_line l
      JOIN supply_replenishment p ON p.id=l.replenishment_id
      WHERE l.item_id=? AND p.id<>? AND p.status IN
      ('draft','submitted','returned','approved','ordered','partially_received') ORDER BY p.id''',
      (item_id, replenishment_id))


def review_inputs(conn, user, replenishment_id):
    with stock._snapshot(conn):
        detail = rep.get_replenishment(conn, user, replenishment_id)
        for line in detail['lines']:
            item = s._item(conn, line['item_id'])
            summary = rep._summary(conn, item)
            line['current_on_hand'] = summary['on_hand']
            line['current_outstanding'] = summary['outstanding']
            line['current_incoming'] = summary['incoming']
            line['current_suggestion'] = max(0, line['intended_target']+summary['outstanding']-summary['on_hand']-summary['incoming'])
            line['overlaps'] = _overlap(conn, detail['id'], line['item_id'])
        current_by_item={line['item_id']:line for line in detail['lines']}
        for submitted_line in detail['submitted_lines']:
            current=current_by_item.get(submitted_line['item_id'])
            if current:
                submitted_line['current_suggestion']=current['current_suggestion']
                submitted_line['current_incoming']=current['current_incoming']
                submitted_line['overlaps']=current['overlaps']
        return detail


def submit_replenishment(conn, user, replenishment_id, *, expected_revision, operation_key, review_reason=''):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        s.require_enabled(conn)
        request = rep._draft(conn, user, replenishment_id)
        revision = s.integer(expected_revision, 'Replenishment revision', 1)
        reason = stock._optional_text(review_reason, 'Changed need or overlap reason', 2000)
        key,digest,prior = operation(conn,user,operation_key,'replenishment_submit',
                                     {'id':request['id'],'revision':revision,'review_reason':reason})
        if prior is not None:return prior
        _revision(request,revision)
        if request['status'] not in ('draft','returned'):
            raise Conflict('Only a draft or returned replenishment can be submitted.')
        lines = rows(conn,'SELECT * FROM supply_replenishment_line WHERE replenishment_id=? ORDER BY id',(request['id'],))
        if not 1 <= len(lines) <= rep.MAX_LINES:raise Invalid('A replenishment needs 1–20 item lines.')
        current=[]
        for line in lines:
            item=s._item(conn,line['item_id'])
            if not item['active'] or any(item[k] != line[k+'_snapshot'] for k in ('code','description','unit')):
                raise Conflict('An item changed. Edit and save the draft before submitting.')
            summary=rep._summary(conn,item)
            fresh=max(0,line['intended_target']+summary['outstanding']-summary['on_hand']-summary['incoming'])
            if (_overlap(conn,request['id'],item['id']) or line['requested_quantity']>fresh) and not reason:
                raise Invalid('Explain overlapping replenishments or demand above the current calculation before submitting.')
            current.append((line,summary))
        now=tz.now_iso();number=request['control_number'] or _number(conn)
        next_revision=request['current_revision']+1
        revision_id=conn.execute('''INSERT INTO supply_replenishment_revision
          (replenishment_id,revision,purpose,procurement_reference,expected_need_date,review_reason,
           submitted_by,submitted_at,operation_key) VALUES (?,?,?,?,?,?,?,?,?)''',
          (request['id'],next_revision,request['purpose'],request['procurement_reference'],
           request['expected_need_date'],reason,user['id'],now,key)).lastrowid
        for line,summary in current:
            conn.execute('''INSERT INTO supply_replenishment_revision_line
              (revision_id,draft_line_id,item_id,code_snapshot,description_snapshot,unit_snapshot,
               requested_quantity,estimated_unit_cost,override_reason,intended_target,suggested_quantity,
               on_hand_snapshot,reserved_snapshot,outstanding_snapshot,incoming_snapshot)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (revision_id,line['id'],line['item_id'],line['code_snapshot'],line['description_snapshot'],line['unit_snapshot'],
               line['requested_quantity'],line['estimated_unit_cost'],line['override_reason'],line['intended_target'],
               max(0,line['intended_target']+summary['outstanding']-summary['on_hand']-summary['incoming']),
               summary['on_hand'],summary['reserved'],summary['outstanding'],summary['incoming']))
        conn.execute('''UPDATE supply_replenishment SET control_number=?,status='submitted',current_revision=?,
          submitted_at=?,revision=revision+1,updated_at=? WHERE id=?''',
          (number,next_revision,now,now,request['id']))
        result={'id':request['id'],'control_number':number,'status':'submitted','revision':revision+1,
                'current_revision':next_revision}
        return record(conn,user,key,digest,'replenishment_submit','replenishment',result,
                      {'review_reason':reason,'submitted_revision_id':revision_id,
                       'lines':[{'item_id':line['item_id'],'requested_quantity':line['requested_quantity'],
                                 'on_hand':summary['on_hand'],'outstanding':summary['outstanding'],
                                 'incoming':summary['incoming']} for line,summary in current]})


def decide_replenishment(conn, user, replenishment_id, fields, *, expected_revision, submitted_revision, operation_key):
    with transaction(conn):
        user=permissions.require_actor(conn,user)
        if not permissions.has_role(conn,user,'replenishment_approver'):
            raise Denied('A current replenishment approver grant is required.')
        s.require_enabled(conn)
        request=rows(conn,'SELECT * FROM supply_replenishment WHERE id=?',(s.integer(replenishment_id,'Replenishment',1),))
        if not request:raise Missing('Replenishment not found.')
        request=request[0]
        if request['prepared_by']==user['id']:raise Denied('You cannot decide a replenishment you prepared.')
        decision=fields.get('decision') if isinstance(fields,dict) else None
        if decision not in ('approved','returned','rejected'):raise Invalid('Choose approve, return or reject.')
        reason=stock._optional_text(fields.get('reason'), 'Decision reason', 2000)
        revision=s.integer(expected_revision,'Replenishment revision',1)
        submitted=s.integer(submitted_revision,'Submitted revision',1)
        raw=fields.get('lines',[])
        if not isinstance(raw,list):raise Invalid('Decision lines are invalid.')
        lines=[]
        if decision=='approved':
            for line in raw:
                if not isinstance(line,dict):raise Invalid('Decision line is invalid.')
                lines.append({'revision_line_id':s.integer(line.get('revision_line_id'),'Submitted line',1),
                              'approved_quantity':s.integer(line.get('approved_quantity'),'Approved quantity'),
                              'reason':stock._optional_text(line.get('reason'),'Line reason',2000)})
        elif not reason:raise Invalid('Explain why the replenishment is returned or rejected.')
        payload={'id':request['id'],'revision':revision,'submitted_revision':submitted,
                 'decision':decision,'reason':reason,'lines':sorted(lines,key=lambda line:line['revision_line_id'])}
        key,digest,prior=operation(conn,user,operation_key,'replenishment_decide',payload)
        if prior is not None:return prior
        _revision(request,revision)
        if request['status']!='submitted' or request['current_revision']!=submitted:
            raise Conflict('This submission has already been decided or replaced. Reload it.')
        submitted_row=rows(conn,'''SELECT * FROM supply_replenishment_revision
          WHERE replenishment_id=? AND revision=?''',(request['id'],submitted))[0]
        revision_lines=rows(conn,'SELECT * FROM supply_replenishment_revision_line WHERE revision_id=? ORDER BY id',
                            (submitted_row['id'],))
        if decision=='approved':
            by_id={line['revision_line_id']:line for line in lines}
            if len(lines)!=len(revision_lines) or set(by_id)!={line['id'] for line in revision_lines}:
                raise Invalid('Decide every submitted line exactly once.')
            if not any(line['approved_quantity'] for line in lines):
                raise Invalid('Approve at least one unit, or return or reject the request.')
            checked=[]
            for submitted_line in revision_lines:
                selected=by_id[submitted_line['id']]
                approved=selected['approved_quantity']
                if approved>submitted_line['requested_quantity']:
                    raise Invalid('Approved quantity cannot exceed the submitted quantity.')
                if approved<submitted_line['requested_quantity'] and not selected['reason']:
                    raise Invalid('Explain every reduced line quantity.')
                item=s._item(conn,submitted_line['item_id'])
                if not item['active']:raise Conflict('An item is inactive. Return the replenishment for revision.')
                summary=rep._summary(conn,item)
                fresh=max(0,submitted_line['intended_target']+summary['outstanding']-summary['on_hand']-summary['incoming'])
                if (approved>fresh or _overlap(conn,request['id'],item['id'])) and not reason:
                    raise Invalid('Explain approval above the current need or alongside another open replenishment.')
                checked.append((submitted_line,selected,summary,fresh))
        else:checked=[]
        now=tz.now_iso()
        decision_id=conn.execute('''INSERT INTO supply_replenishment_decision
          (replenishment_id,revision_id,decision,decided_by,decided_at,reason,operation_key)
          VALUES (?,?,?,?,?,?,?)''',(request['id'],submitted_row['id'],decision,user['id'],now,reason,key)).lastrowid
        for submitted_line,selected,summary,fresh in checked:
            conn.execute('''INSERT INTO supply_replenishment_decision_line
              (decision_id,revision_line_id,approved_quantity,reason,current_suggestion,
               current_on_hand,current_outstanding,current_incoming) VALUES (?,?,?,?,?,?,?,?)''',
              (decision_id,submitted_line['id'],selected['approved_quantity'],selected['reason'],fresh,
               summary['on_hand'],summary['outstanding'],summary['incoming']))
            conn.execute('INSERT INTO supply_replenishment_commitment(line_id,approved_quantity) VALUES (?,?)',
                         (submitted_line['draft_line_id'],selected['approved_quantity']))
        conn.execute('''UPDATE supply_replenishment SET status=?,revision=revision+1,updated_at=? WHERE id=?''',
                     (decision,now,request['id']))
        result={'id':request['id'],'status':decision,'revision':revision+1,'decision_id':decision_id}
        return record(conn,user,key,digest,'replenishment_decide','replenishment',result,
                      {'submitted_revision':submitted,'reason':reason,'lines':[
                          {'item_id':line['item_id'],'approved_quantity':selected['approved_quantity'],
                           'current_suggestion':fresh} for line,selected,_summary,fresh in checked]})


def record_order(conn, user, replenishment_id, fields, *, expected_revision, operation_key):
    with transaction(conn):
        user=permissions.require_custodian(conn,user);s.require_enabled(conn)
        request=rows(conn,'SELECT * FROM supply_replenishment WHERE id=?',(s.integer(replenishment_id,'Replenishment',1),))
        if not request:raise Missing('Replenishment not found.')
        request=request[0]
        revision=s.integer(expected_revision,'Replenishment revision',1)
        reference=s.text(fields.get('order_reference'),'Order reference',120)
        delivery=stock._date(fields.get('expected_delivery_date'),'Expected delivery date')
        responsible=s.integer(fields.get('responsible_custodian_id'),'Responsible custodian',1)
        raw=fields.get('lines')
        if not isinstance(raw,list):raise Invalid('Order quantities are required.')
        lines=[{'line_id':s.integer(line.get('line_id'),'Line',1),
                'ordered_quantity':s.integer(line.get('ordered_quantity'),'Ordered quantity')}
               for line in raw if isinstance(line,dict)]
        payload={'id':request['id'],'revision':revision,'reference':reference,'delivery':delivery,
                 'responsible':responsible,'lines':sorted(lines,key=lambda line:line['line_id'])}
        key,digest,prior=operation(conn,user,operation_key,'replenishment_order',payload)
        if prior is not None:return prior
        _revision(request,revision)
        if request['status']!='approved':raise Conflict('Only an approved replenishment can be marked ordered.')
        responsible_user=permissions.require_actor(conn,{'id':responsible})
        if not permissions.has_role(conn,responsible_user,'custodian'):
            raise Invalid('Choose an active supply custodian as responsible person.')
        commitments=rows(conn,'''SELECT c.*,l.item_id FROM supply_replenishment_commitment c
          JOIN supply_replenishment_line l ON l.id=c.line_id WHERE l.replenishment_id=? ORDER BY c.line_id''',(request['id'],))
        by_id={line['line_id']:line for line in lines}
        if len(lines)!=len(commitments) or set(by_id)!={c['line_id'] for c in commitments}:
            raise Invalid('Record an ordered quantity for every approved line.')
        if not any(line['ordered_quantity'] for line in lines):raise Invalid('Order at least one unit.')
        for commitment in commitments:
            if by_id[commitment['line_id']]['ordered_quantity']>commitment['approved_quantity']-commitment['cancelled_quantity']:
                raise Invalid('Ordered quantity cannot exceed the active approved quantity.')
        now=tz.now_iso()
        order_id=conn.execute('''INSERT INTO supply_replenishment_order
          (replenishment_id,order_reference,expected_delivery_date,responsible_custodian_id,
           ordered_by,ordered_at,operation_key) VALUES (?,?,?,?,?,?,?)''',
          (request['id'],reference,delivery,responsible,user['id'],now,key)).lastrowid
        for commitment in commitments:
            conn.execute('INSERT INTO supply_replenishment_order_line(order_id,line_id,ordered_quantity) VALUES (?,?,?)',
                         (order_id,commitment['line_id'],by_id[commitment['line_id']]['ordered_quantity']))
        conn.execute("UPDATE supply_replenishment SET status='ordered',revision=revision+1,updated_at=? WHERE id=?",(now,request['id']))
        result={'id':request['id'],'status':'ordered','revision':revision+1,'order_id':order_id}
        return record(conn,user,key,digest,'replenishment_order','replenishment',result,payload)


def cancel_replenishment_remainder(conn, user, replenishment_id, fields, *, expected_revision, operation_key):
    with transaction(conn):
        user=permissions.require_custodian(conn,user);s.require_enabled(conn)
        request=rows(conn,'SELECT * FROM supply_replenishment WHERE id=?',(s.integer(replenishment_id,'Replenishment',1),))
        if not request:raise Missing('Replenishment not found.')
        request=request[0]
        revision=s.integer(expected_revision,'Replenishment revision',1)
        reason=s.text(fields.get('reason'),'Cancellation reason',2000)
        raw=fields.get('lines')
        if not isinstance(raw,list) or not raw:raise Invalid('Select at least one unreceived line remainder.')
        lines=[{'line_id':s.integer(line.get('line_id'),'Line',1),
                'cancelled_quantity':s.integer(line.get('cancelled_quantity'),'Cancellation quantity',1)}
               for line in raw if isinstance(line,dict)]
        payload={'id':request['id'],'revision':revision,'reason':reason,
                 'lines':sorted(lines,key=lambda line:line['line_id'])}
        key,digest,prior=operation(conn,user,operation_key,'replenishment_cancel_remainder',payload)
        if prior is not None:return prior
        _revision(request,revision)
        if request['status'] not in ('approved','ordered','partially_received'):
            raise Conflict('Only an approved, ordered or partly received replenishment has a cancellable remainder.')
        commitments=rows(conn,'''SELECT c.* FROM supply_replenishment_commitment c
          JOIN supply_replenishment_line l ON l.id=c.line_id WHERE l.replenishment_id=?''',(request['id'],))
        by_id={c['line_id']:c for c in commitments}
        if len(lines)!=len({line['line_id'] for line in lines}) or any(line['line_id'] not in by_id for line in lines):
            raise Invalid('Choose distinct approved lines from this replenishment.')
        for line in lines:
            c=by_id[line['line_id']]
            if line['cancelled_quantity']>c['approved_quantity']-c['received_quantity']-c['cancelled_quantity']:
                raise Invalid('Cancellation cannot exceed the unreceived approved remainder.')
        now=tz.now_iso()
        cancellation_id=conn.execute('''INSERT INTO supply_replenishment_cancellation
          (replenishment_id,reason,cancelled_by,cancelled_at,operation_key) VALUES (?,?,?,?,?)''',
          (request['id'],reason,user['id'],now,key)).lastrowid
        for line in lines:
            conn.execute('''UPDATE supply_replenishment_commitment SET cancelled_quantity=cancelled_quantity+?
              WHERE line_id=?''',(line['cancelled_quantity'],line['line_id']))
            conn.execute('''INSERT INTO supply_replenishment_cancellation_line
              (cancellation_id,line_id,cancelled_quantity) VALUES (?,?,?)''',
              (cancellation_id,line['line_id'],line['cancelled_quantity']))
        remaining=conn.execute('''SELECT COALESCE(SUM(c.approved_quantity-c.received_quantity-c.cancelled_quantity),0)
          FROM supply_replenishment_commitment c JOIN supply_replenishment_line l ON l.id=c.line_id
          WHERE l.replenishment_id=?''',(request['id'],)).fetchone()[0]
        received=conn.execute('''SELECT COALESCE(SUM(c.received_quantity),0)
          FROM supply_replenishment_commitment c JOIN supply_replenishment_line l ON l.id=c.line_id
          WHERE l.replenishment_id=?''',(request['id'],)).fetchone()[0]
        status=('received' if received else 'cancelled') if remaining==0 else request['status']
        conn.execute('UPDATE supply_replenishment SET status=?,revision=revision+1,updated_at=? WHERE id=?',
                     (status,now,request['id']))
        result={'id':request['id'],'status':status,'revision':revision+1,'remaining_incoming':remaining,
                'cancellation_id':cancellation_id}
        return record(conn,user,key,digest,'replenishment_cancel_remainder','replenishment',result,payload)
