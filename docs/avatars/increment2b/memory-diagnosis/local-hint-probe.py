import json,os,shutil
from pathlib import Path
from tests.test_avatar_baseline_browser import baseline_server,PROBE,snapshot

def test_probe(baseline_server):
 from playwright.sync_api import sync_playwright
 origin,cookie,_=baseline_server
 output=Path(os.environ['CSS_AVATAR_OUT']);output.mkdir(parents=True,exist_ok=True)
 result=[]
 with sync_playwright() as pw:
  for mode in ['current','no-hint','no-hint','current']:
   browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
   context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC')
   context.add_cookies([cookie]);context.add_init_script(PROBE)
   page=context.new_page();cdp=context.new_cdp_session(page);cdp.send('LayerTree.enable')
   latest={}
   def layers(data):latest.update(data)
   cdp.on('LayerTree.layerTreeDidChange',layers)
   page.goto(origin+'/me')
   if mode=='no-hint':page.add_style_tag(content='.avcard .avmove,.gl-art .avmove{will-change:auto}')
   for radio in page.locator('input[name="avatar_kind"]').all():
    radio.check(force=True);radio.scroll_into_view_if_needed();page.wait_for_timeout(50)
   page.locator('#companion-growth-title').scroll_into_view_if_needed();page.wait_for_timeout(500)
   data={'mode':mode,'snapshot':snapshot(page,cdp),'layers':latest}
   for layer in data['layers'].get('layers',[]):
    try:layer['reasons']=cdp.send('LayerTree.compositingReasons',{'layerId':layer['layerId']})
    except Exception:pass
   result.append(data);context.close();browser.close()
 (output/'probe.json').write_text(json.dumps(result,indent=2))
