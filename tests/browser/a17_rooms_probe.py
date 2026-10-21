"""Explicit local axe evidence; excluded from ordinary test collection.

Use A17_AXE_PATH for the separately installed axe-core 4.14.0 engine and
A17_REPORT for the sanitized output. Only synthetic local room data is used.
"""
import hashlib
import json
import os
from pathlib import Path

import auth
import rooms
import storage as st
from tests.conftest import join_admin_section, session_token
from tests.test_rooms_guidance_browser import browser, conn, room_page, goto, set_day
from tests.test_rooms_pages import bookable_day, slot_id


def test_probe(room_page, viewer):
    page, state, conn, context = room_page
    engine = Path(os.environ['A17_AXE_PATH'])
    uid = st.get_admin_user(conn,'viewer@test.local')['id']
    day = bookable_day(conn)
    records = []
    for hour, status in [(9,'approved'), (11,'requested'), (13,'declined'), (15,'withdrawn')]:
        res = rooms.request(conn,title='Example ' + status,day=day,slot_ids=[slot_id(conn,hour)],requester_user_id=uid)
        if status == 'approved':rooms.approve(conn,res['id'],'example-approver')
        if status == 'declined':rooms.decline(conn,res['id'],'example-approver','Choose another time')
        if status == 'withdrawn':rooms.withdraw(conn,res['id'],uid)
        records.append(res)
    guest = rooms.request_external(conn,name='Example guest',org='Example',email='guest@example.test',phone='',
        consent=True,title='Example guest meeting',day=day,slot_ids=[slot_id(conn,17)])
    guest_path = '/room/t/' + auth.make_room_track_token(guest['id'])
    owner_token = session_token(st.get_admin_user_by_id(conn,uid))
    admin_id = st.get_admin_user(conn,'admin@test.local')['id']
    join_admin_section(conn,admin_id)
    admin_token = session_token(st.get_admin_user_by_id(conn,admin_id))
    results = []

    def scan(surface, width, theme):
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        page.add_script_tag(path=str(engine))
        assert page.evaluate('axe.version') == '4.14.0'
        result = page.evaluate('''async () => {
          const r=await axe.run(document,{runOnly:{type:'tag',values:[
            'wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
          const items=vs=>vs.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));
          return {violations:items(r.violations),incomplete:items(r.incomplete),
            overflow:document.documentElement.scrollWidth>innerWidth};
        }''')
        result.update(surface=surface,width=width,theme=theme)
        results.append(result)

    for theme in ('light','dark'):
        for width in (1440,390):
            page.set_viewport_size({'width':width,'height':1000 if width>400 else 844})
            viewer.cookies.set(auth.COOKIE_NAME,owner_token)
            goto(page,'/rooms?week=' + day.isoformat())
            scan('Availability board',width,theme)
            if width < 1200:page.locator('#rm-open').click()
            set_day(page,day)
            page.wait_for_function('!document.getElementById("rm-clash").textContent.includes("Checking")')
            scan('Request panel',width,theme)
            if width < 1200:page.keyboard.press('Escape')
            page.goto('/rooms/mine')
            scan('My reservations',width,theme)
            if width==390 and theme=='light':page.screenshot(path='/tmp/a17-mine-mobile.png',full_page=False)
            page.goto(guest_path + '?new=1')
            scan('Guest tracking',width,theme)
            viewer.cookies.set(auth.COOKIE_NAME,admin_token)
            page.goto('/approvals#rooms')
            scan('Room approvals',width,theme)
            viewer.cookies.set(auth.COOKIE_NAME,owner_token)
            goto(page,'/rooms?date=' + day.isoformat())
            if width < 1200:page.locator('#rm-open').click()
            page.locator('#rm-title').fill('Conflict recovery example')
            page.get_by_role('button',name='Request room',exact=True).click()
            page.locator('#rm-form-error').wait_for()
            scan('Server conflict with retained draft',width,theme)
            if width==390 and theme=='light':page.screenshot(path='/tmp/a17-conflict-mobile.png',full_page=False)
    report = {'axe':'4.14.0','engine_sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),
        'browser':context.browser.version,'checks':results,'errors':state['errors'],
        'notes':'Synthetic local authenticated requester/approver and guest data. Four intentional rejected requests. No production access or screen-reader session.'}
    Path(os.environ['A17_REPORT']).write_text(json.dumps(report,indent=2)+'\n')
    failures = [(r['surface'],r['width'],r['theme'],[(v['id'],len(v['nodes'])) for v in r['violations']])
                for r in results if r['violations']]
    assert not failures, failures
