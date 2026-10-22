import os,sys,tempfile,threading,time
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
out=ROOT/'docs/evidence/supplies-s6-2';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='supplies-s62-') as directory:
    os.environ.update(CSS_DB=str(Path(directory)/'test.db'),CSS_BASE_URL='http://127.0.0.1:8791',CSS_SECURE_COOKIES='0')
    import storage as st
    c=st.connect(os.environ['CSS_DB']);st.init_db(c);c.close()
    import app,auth,supplies as s,supplies_stock as stock,supplies_replenishment as rep,supplies_reports as reports,uvicorn
    app.DB=os.environ['CSS_DB'];c=st.connect(app.DB);st.init_db(c)
    unit=st.add_org_unit(c,'Synthetic section','section','SYN/SECTION');users=[]
    for name,role in [('admin','admin'),('custodian','viewer'),('A','viewer'),('approver','viewer'),('B','viewer')]:
        uid=st.create_admin_user(c,name+'@example.test','unused','unused',role,active=True);st.mark_onboarded(c,uid)
        rp=st.add_rp(c,'Synthetic '+name,True,unit);c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,uid));c.commit()
        users.append(st.get_admin_user_by_id(c,uid))
    admin,custodian,a,approver,b=users
    s.grant_role(c,admin,custodian['id'],'custodian',operation_key=str(uuid4()))
    s.grant_role(c,admin,approver['id'],'request_approver',unit_id=unit,operation_key=str(uuid4()))
    s.grant_role(c,admin,b['id'],'replenishment_approver',operation_key=str(uuid4()))
    s.set_enabled(c,admin,'1',expected_revision=0,operation_key=str(uuid4()))
    item=s.create_item(c,custodian,{'code':'SYN-PAPER','description':'Synthetic paper','unit':'Ream','critical_level':'5','target_level':'20'},operation_key=str(uuid4()))['id']
    stock.post_opening(c,custodian,item,{'quantity':'10','effective_date':'2026-10-19','reason':'Synthetic opening'},expected_revision=1,operation_key=str(uuid4()))
    server=uvicorn.Server(uvicorn.Config(app.app,host='127.0.0.1',port=8791,lifespan='off',log_level='warning'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(200):
        if server.started:break
        time.sleep(.05)
    assert server.started
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            base='http://127.0.0.1:8791'
            def login(user):page.context.add_cookies([{'name':auth.COOKIE_NAME,'value':app._issue_session(user),'url':base}])
            def shot(name):
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(out/name),full_page=True)
            def state(expected):
                row=rep.suggest_replenishment(c,custodian,item)
                got=tuple(row[k] for k in ('on_hand','reserved','available','outstanding','incoming'))
                assert got==expected,(got,expected,page.url)
            def make_request(user,qty):
                login(user);page.goto(base+'/supplies/requests/new')
                page.get_by_label('Purpose').fill('Synthetic supply need')
                page.get_by_label('Supply item 1',exact=True).select_option(str(item))
                page.get_by_label('Requested quantity 1',exact=True).fill(str(qty))
                page.get_by_role('button',name='Save draft').click()
                rid=int(page.url.rstrip('/').split('/')[-1])
                page.get_by_role('button',name='Submit for approval').click()
                return rid
            def approve_request(rid,approved_qty):
                login(approver);page.goto(f'{base}/supplies/requests/{rid}')
                page.get_by_label('Approved quantity for SYN-PAPER').fill(str(approved_qty))
                if approved_qty==6:page.get_by_label('Reduction reason for SYN-PAPER').fill('Synthetic reviewed reduction')
                page.get_by_role('button',name='Record decision').click()
            def issue_request(rid,qty):
                login(custodian);page.goto(f'{base}/supplies/requests/{rid}/issues/new')
                page.get_by_label('Handover date').fill('2026-10-20')
                page.get_by_label('Issue quantity for SYN-PAPER (Ream)').fill(str(qty))
                page.get_by_role('checkbox').check()
                page.get_by_role('button',name='Post supply handover').click()
                assert '/supplies/issues/' in page.url,page.url
                return int(page.url.rstrip('/').split('/')[-1])
            state((10,0,10,0,0))
            a_id=make_request(a,8);approve_request(a_id,6);state((10,6,4,6,0))
            b_id=make_request(b,7);approve_request(b_id,7);state((10,10,0,13,0))
            a_issue=issue_request(a_id,4);state((6,6,0,9,0));shot('partial-issue-mobile.png')
            login(a);page.goto(f'{base}/supplies/requests/{a_id}')
            page.get_by_text('Cancel remaining demand',exact=True).click()
            page.get_by_role('checkbox').check();page.get_by_label('Cancellation reason').fill('Synthetic remainder no longer needed')
            page.get_by_role('button',name='Cancel selected remainders').click();state((6,6,0,7,0))
            login(custodian);page.goto(f'{base}/supplies/replenishments/new?item_id={item}')
            page.locator('textarea[name=purpose]').fill('Synthetic replenishment')
            page.locator('select[name=item_id_0]').select_option(str(item))
            page.locator('input[name=quantity_0]').fill('21')
            page.locator('input[name=target_0]').fill('20')
            page.get_by_role('button',name='Save draft').click()
            rid=int(page.url.rstrip('/').split('/')[-1])
            page.get_by_role('button',name='Submit replenishment').click()
            login(b);page.goto(f'{base}/supplies/replenishments/{rid}')
            page.get_by_role('button',name='Record replenishment decision').click();state((6,6,0,7,21))
            def delivery(qty,number):
                login(custodian);page.goto(f'{base}/supplies/replenishments/{rid}/deliveries/new')
                page.get_by_label('Supplier').fill('Synthetic supplier')
                page.get_by_label('DR number').fill(number)
                page.get_by_label('Delivered',exact=True).fill(str(qty))
                page.get_by_label('Accepted',exact=True).fill(str(qty))
                page.get_by_label('Rejected',exact=True).fill('0')
                page.get_by_role('button',name='Record delivery').click()
                assert '/deliveries/' in page.url,page.url
            delivery(10,'DR-SYN-1');state((16,7,9,7,11));shot('partial-delivery-mobile.png')
            b_issue=issue_request(b_id,7);state((9,0,9,0,11))
            login(b);page.goto(f'{base}/supplies/issues/{b_issue}')
            page.get_by_role('button',name='Record recipient response').click()
            delivery(11,'DR-SYN-2');state((20,0,20,0,0))
            login(custodian);page.goto(f'{base}/supplies/issues/{b_issue}/returns')
            page.get_by_label('Original item line').select_option(index=1)
            page.get_by_label('Quantity to return').fill('1')
            page.get_by_label('Condition of returned supplies').select_option('usable')
            page.get_by_label('Effective date').fill('2026-10-20')
            page.get_by_label('Reason and evidence').fill('Synthetic usable return')
            page.get_by_role('button',name='Review correction impact').click()
            page.get_by_role('checkbox').check()
            page.get_by_role('button',name='Post reviewed correction').click();state((21,0,21,0,0))
            page.goto(f'{base}/supplies/reports/stock-card?item_id={item}')
            expect(page.get_by_role('region',name='Stock card')).to_contain_text('DR-SYN-2')
            shot('final-stock-card-mobile.png')
            page.goto(base+'/supplies/reports/inventory');shot('final-inventory-mobile.png')
            data=reports.report(c,custodian,'consumption')
            assert data['summary'][0]['net_issued']==11 and data['summary'][0]['usable_returned']==1
            assert len(reports.report(c,custodian,'stock-card',item_id=item)['rows'])==6
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            assert not errors,errors
            browser.close()
        print('PASS: Chromium browser-to-route-to-service-to-ledger-to-report exact section 9 scenario')
    finally:server.should_exit=True;thread.join(timeout=5);c.close()
