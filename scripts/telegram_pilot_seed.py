"""Native synthetic fixtures for the disposable pilot; no production imports at module load."""
from datetime import timedelta
from uuid import uuid4


def seed(database, passwords):
    import auth
    import documents as docs
    import storage as st
    import supplies
    import supplies_requests
    import supplies_stock
    import supplies_approvals
    import rooms
    import meals
    import travel
    import work_blockers
    import work_updates
    import work
    import work_tasks
    import work_discussion
    import tzutil as tz
    conn = st.connect(str(database))
    try:
        st.init_db(conn)
        if st.count_admin_users(conn):
            raise ValueError('Pilot seed requires an empty database.')
        st.get_or_create_blhsd(conn)
        unit = st.add_org_unit(conn, 'Synthetic Pilot Division', 'division', 'PILOT/D1')
        admin_unit = st.add_org_unit(conn, 'Synthetic Administrative Section', 'section', 'PILOT/ADMIN')
        other_unit = st.add_org_unit(conn, 'Synthetic Restricted Division', 'division', 'PILOT/D2')
        users = {}
        for alias in ('staff', 'officer', 'peer', 'admin'):
            rp = st.add_rp(conn, 'Pilot ' + alias.title(), True, admin_unit if alias == 'admin' else unit, email=f'pilot-{alias}@example.invalid')
            hashed, salt = auth.hash_password(passwords[alias])
            uid = st.create_admin_user(conn, f'pilot-{alias}@example.invalid', hashed, salt,
                                       'admin' if alias == 'admin' else 'viewer',
                                       rp_id=rp, created_by='synthetic pilot')
            st.mark_onboarded(conn, uid)
            users[alias] = st.get_admin_user_by_id(conn, uid)
        admin, officer, staff, peer = (users[x] for x in ('admin', 'officer', 'staff', 'peer'))
        setup = docs.preview_admin_setup(conn, admin, admin['username'], 'Isolated synthetic pilot setup')
        docs.bootstrap_admins(conn, admin, setup)
        docs.set_module_enabled(conn, admin, True, 0, 'Synthetic pilot source fixtures')
        docs.grant(conn, admin, officer['id'], 'records', unit=unit)
        work.set_module_enabled(conn, admin, True, st.get_setting(conn, 'documents.settings_revision'), 'Synthetic pilot')
        doc = docs.register(conn, staff, {'subject': 'PILOT permitted document', 'type': 'request', 'unit_id': unit})
        doc = docs.mutate(conn, officer, doc['id'], doc['revision'], 'verify', {'verification': 'verified', 'reason': 'Synthetic verification'})
        hidden = docs.register(conn, admin, {'subject': 'PILOT restricted document', 'type': 'request', 'unit_id': other_unit})
        item = work.create(conn, staff, {'title': 'PILOT shared work', 'outcome': 'Synthetic acceptance', 'unit_id': unit,
                                         'source_document_id': doc['id']})
        item = work.confirm_lead(conn, officer, item['id'], item['revision'], officer['id'], 'Pilot lead')
        tasks = {}
        for state in ('proposed', 'todo', 'in_progress', 'for_review', 'done', 'cancelled', 'peer'):
            task = work_tasks.create(conn, staff, item['id'], {'title': 'PILOT ' + state,
                'expected_output': 'Synthetic output', 'unit_id': unit})
            if state != 'proposed':
                task = work_tasks.mutate(conn, officer, item['id'], task['id'], task['revision'], 'confirm',
                    {'owner_id': peer['id'] if state == 'peer' else staff['id'], 'reason': 'Pilot assignment'})
            for action, states in [('acknowledge', ('in_progress','for_review','done')),
                                   ('submit', ('for_review','done')), ('accept', ('done',)), ('cancel', ('cancelled',))]:
                if state in states:
                    task = work_tasks.mutate(conn, officer, item['id'], task['id'], task['revision'], action,
                        {'reason': 'Pilot transition', 'submission': 'Synthetic review evidence'})
            tasks[state] = task['id']
        hidden_case = work.create(conn, admin, {'title': 'PILOT restricted work', 'outcome': 'Denied to staff',
            'unit_id': other_unit, 'source_document_id': hidden['id']})
        work_updates.follow(conn, staff, item['id'])
        comment = work_discussion.post(conn, staff, item['id'], 'PILOT original discussion')
        work_discussion.post(conn, peer, item['id'], 'PILOT peer reply', parent_id=comment)
        work_discussion.edit(conn, staff, item['id'], None, comment, 1, 'PILOT edited discussion')
        work_discussion.post(conn, staff, item['id'], 'PILOT long Unicode ' + 'Example 📌 ' * 250, task_id=tasks['todo'])
        supplies.grant_role(conn, admin, admin['id'], 'custodian', operation_key=str(uuid4()))
        supplies.grant_role(conn, admin, officer['id'], 'request_approver', unit_id=unit, operation_key=str(uuid4()))
        supplies.set_enabled(conn, admin, '1', expected_revision=0, operation_key=str(uuid4()))
        stock = supplies.create_item(conn, admin, {'code':'PILOT-PAPER', 'description':'Synthetic pilot paper',
            'unit':'Ream', 'critical_level':'5', 'target_level':'20'}, operation_key=str(uuid4()))
        supplies_stock.post_opening(conn, admin, stock['id'], {'quantity':'100',
            'effective_date':tz.today_local().isoformat(), 'reason':'Synthetic opening'},
            expected_revision=stock['revision'], operation_key=str(uuid4()))
        requests = {}
        for alias in ('staff', 'peer'):
            req = supplies_requests.save_draft(conn, users[alias], {'purpose':'PILOT own draft',
                'date_needed':None, 'lines':[{'item_id':stock['id'], 'requested_quantity':2}]}, operation_key=str(uuid4()))
            requests[alias] = req['id']
        for label in ('returned', 'submitted'):
            req = supplies_requests.save_draft(conn, staff, {'purpose':'PILOT ' + label,
                'date_needed':None, 'lines':[{'item_id':stock['id'], 'requested_quantity':1}]}, operation_key=str(uuid4()))
            req = supplies_requests.submit(conn, staff, req['id'], expected_revision=req['revision'], operation_key=str(uuid4()))
            if label == 'returned':
                supplies_approvals.decide_request(conn, officer, req['id'], {'decision':'returned','reason':'Synthetic revision needed'},
                    expected_revision=req['revision'], submitted_revision=req['current_revision'], operation_key=str(uuid4()))
            requests[label] = req['id']
        day = tz.today_local() + timedelta(days=1)
        while not rooms.is_working_day(conn, day):
            day += timedelta(days=1)
        meeting = st.cal_create(conn, 'PILOT plain meeting', day.isoformat(), start_time='10:00', end_time='11:00',
            by=staff['username'], audience='people', people=[staff['id'], officer['id']])
        rooms.ensure_slots(conn)
        slots = rooms.list_slots(conn)
        pending = rooms.request(conn, title='PILOT pending room', day=day,
            slot_ids=[slots[0]['id']], requester_user_id=staff['id'], quiet=True)
        approved = rooms.request(conn, title='PILOT approved room', day=day,
            slot_ids=[slots[-1]['id']], requester_user_id=staff['id'], quiet=True)
        assert rooms.is_room_admin(conn, admin)
        rooms.approve(conn, approved['id'], admin['username'], notify=False)
        work_blockers.mutate(conn, officer, item['id'], tasks['todo'], 2, 'dependency_add',
            {'prerequisite_id':tasks['in_progress'], 'reason':'Synthetic prerequisite'})
        work_blockers.mutate(conn, officer, item['id'], tasks['in_progress'], 3, 'block',
            {'reason':'Synthetic blocker', 'followup_owner_id':staff['id'], 'followup_date':day.isoformat()})
        personal = {}
        meal_day = rooms.add_working_days(conn, tz.today_local(), 6)
        period = st.work_arrangement_open_periods()[0]
        for alias in ('staff', 'peer'):
            user = users[alias]
            filing = travel.create_filing(conn, user, kind='reimbursement',
                source={'source_kind':'blank', 'title':'PILOT travel',
                        'start':(tz.today_local()-timedelta(days=2)).isoformat(),
                        'end':(tz.today_local()-timedelta(days=1)).isoformat(), 'venue':'Synthetic venue'},
                answers={}, role='participant', dpo_no='PILOT-NOT-REAL', today=tz.today_local())
            meal = meals.create(conn, user, title='PILOT meal', day=meal_day.isoformat(),
                venue='Synthetic venue', pax=3, special_request='Synthetic note', wanted=['lunch'], times={'lunch':'12:00'})
            arrangement = st.create_work_arrangement(conn, user['id'], period, 'REG', note='Synthetic request')
            personal[alias] = {'travel':filing['id'], 'meal':meal['id'], 'arrangement':arrangement}
        # This non-secret index stays inside the disposable DB; source pages remain authoritative.
        import json
        fixtures = {'work':item['id'], 'restricted_work':hidden_case['id'], 'document':doc['id'],
                    'restricted_document':hidden['id'], 'tasks':tasks, 'supply_drafts':requests,
                    'catalog_item':stock['id'], 'meeting':meeting, 'day':day.isoformat(),
                    'rooms':{'pending':pending['id'], 'approved':approved['id']}, 'personal':personal}
        st.set_setting(conn, 'telegram.pilot.fixtures', json.dumps(fixtures))
        return fixtures
    finally:
        conn.close()
