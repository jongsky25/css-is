"""Temporary diagnostic: inspect whether native allocation stacks are symbolized."""
import gzip,json,os,shutil
from pathlib import Path
from tests.test_avatar_baseline_browser import baseline_server,PROBE

def test_native_sampling(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC',service_workers='block')
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();page.goto(origin+'/?view=me');session=context.new_cdp_session(page)
        session.send('Memory.startSampling',{'samplingInterval':32768})
        page.goto(origin+'/me')
        for radio in page.locator('input[name="avatar_kind"]').all():
            radio.check(force=True);radio.scroll_into_view_if_needed();page.wait_for_timeout(50)
        result=session.send('Memory.getSamplingProfile')
        out=Path(os.environ['CSS_AVATAR_OUT']);out.mkdir(parents=True,exist_ok=True)
        with gzip.open(out/'native-profile.json.gz','wt') as f:json.dump(result,f)
        print(json.dumps({'sample_count':len(result['profile']['samples']),'first_stacks':[x['stack'] for x in result['profile']['samples'][:3]]}))
        session.send('Memory.stopSampling');context.close();browser.close()
