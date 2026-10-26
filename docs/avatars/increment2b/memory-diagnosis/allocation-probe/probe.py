import gzip,json,os,shutil,time
from pathlib import Path
from tests.test_avatar_baseline_browser import baseline_server,PROBE,snapshot

def test_allocations(baseline_server):
 from playwright.sync_api import sync_playwright
 origin,cookie,_=baseline_server
 output=Path(os.environ['CSS_AVATAR_OUT']);output.mkdir(parents=True,exist_ok=True)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC')
  context.add_cookies([cookie]);context.add_init_script(PROBE)
  page=context.new_page();cdp=context.new_cdp_session(page);done=[]
  cdp.on('Tracing.tracingComplete',lambda e:done.append(e))
  cdp.send('Tracing.start',{'traceConfig':{'recordMode':'recordUntilFull','includedCategories':['disabled-by-default-memory-infra'],'memoryDumpConfig':{}},'transferMode':'ReturnAsStream'})
  page.goto(origin+'/?view=me');page.wait_for_timeout(1000)
  home=cdp.send('Tracing.requestMemoryDump',{'levelOfDetail':'detailed'})
  page.goto(origin+'/me')
  for radio in page.locator('input[name="avatar_kind"]').all():
   radio.check(force=True);radio.scroll_into_view_if_needed();page.wait_for_timeout(50)
  page.locator('#companion-growth-title').scroll_into_view_if_needed();page.wait_for_timeout(500)
  picker=cdp.send('Tracing.requestMemoryDump',{'levelOfDetail':'detailed'})
  observed=snapshot(page,cdp)
  cdp.send('Tracing.end')
  deadline=time.monotonic()+30
  while not done:
   assert time.monotonic()<deadline
   page.wait_for_timeout(100)
  stream=done[0]['stream'];chunks=[]
  while True:
   part=cdp.send('IO.read',{'handle':stream});chunks.append(part['data'])
   if part.get('eof'):break
  cdp.send('IO.close',{'handle':stream})
  with gzip.open(output/'memory-trace.json.gz','wt') as f:f.write(''.join(chunks))
  (output/'observed.json').write_text(json.dumps({'home_dump':home,'picker_dump':picker,'picker':observed},indent=2))
  context.close();browser.close()
