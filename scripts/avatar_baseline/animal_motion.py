"""Freeze real animal rig reactions at each stage/mood and check reduced motion."""
import argparse
import os
import json
import re
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
from gallery import render

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
rigs={'dog':('wag','.av-tail','av-wag'),'rabbit':('ear','.av-ear-l','av-earflick'),'bird':('flap','.av-wing-l','av-flap-l'),'turtle':('hide','.av-head','av-retract')}
rigs.update({'fish':('fin','.av-fin-t','av-fin'),'dolphin':('fin','.av-fin-t','av-fin'),'owl':('turn','.av-head','av-headturn'),'bat':('flap','.av-wing-l','av-flap-l')})
rigs={k:v for k,v in rigs.items() if k in os.getenv('CSS_AVATAR_BATCH_KINDS','dog,rabbit,bird,turtle').split(',')}
rows=[]
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
 for theme in ['light','dark','contrast']:
  c=b.new_context(viewport={'width':1440,'height':1000});page=c.new_page()
  page.set_content(re.sub(r'<script\b[^>]*>.*?</script>','',render('gallery',theme),flags=re.S))
  page.locator('article').evaluate_all('(els,kinds)=>els.forEach(e=>{if(!kinds.includes(e.querySelector("svg").dataset.avatarKind))e.remove()})',list(rigs))
  for kind,(reaction,hook,animation) in rigs.items():
   wraps=page.locator(f'.avwrap[data-kind="{kind}"]');assert wraps.count()==18
   wraps.evaluate_all('(els,reaction)=>els.forEach(e=>{e.setAttribute("data-interactive","");e.classList.add("av-do-"+reaction)})',reaction)
   assert wraps.locator(hook).count()==18
   assert wraps.locator(hook).evaluate_all('(es)=>es.every(e=>getComputedStyle(e).animationName!=="none")')
  page.evaluate('document.getAnimations().forEach(a=>{a.pause();a.currentTime=a.animationName==="av-retract"?900:450})')
  page.screenshot(path=str(a.out/f'reactions-{theme}.png'),full_page=True)
  for kind,(_,hook,animation) in rigs.items():
   for wrapper in page.locator(f'.avwrap[data-kind="{kind}"]').all():
    assert wrapper.locator(hook).first.evaluate('(e)=>getComputedStyle(e).animationName')==animation
    assert wrapper.locator('svg[data-avatar-kind]').evaluate('(e)=>getComputedStyle(e).filter')=='none'
    if kind=='turtle':
     wrapper.scroll_into_view_if_needed()
     hidden=wrapper.evaluate('''e=>{const eye=e.querySelector('.av-eye'),r=eye.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return !!top&&e.contains(top)&&!e.querySelector('.av-head').contains(top)}''')
     assert hidden, 'Turtle face is still exposed during hiding'
    rows.append({'theme':theme,'kind':kind,'stage':wrapper.locator('svg[data-avatar-kind]').get_attribute('data-avatar-stage'),'mood':wrapper.get_attribute('data-mood'),'animation':animation})
  page.emulate_media(reduced_motion='reduce')
  assert page.locator('.avwrap svg *').evaluate_all('(es)=>es.every(e=>getComputedStyle(e).animationName==="none")')
  c.close()
 b.close()
(a.out/'motion-rig-check.json').write_text(json.dumps({'cases':len(rows),'reduced_motion_themes':3,'rows':rows},indent=2))
print(len(rows),'real rig stage/mood/theme cases passed')
