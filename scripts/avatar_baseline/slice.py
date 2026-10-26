"""Before/after slice gallery and recordings, using real old/new Jinja macros."""
import argparse
from itertools import count
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from playwright.sync_api import sync_playwright
from gallery import ROOT, CATALOG

p=argparse.ArgumentParser();p.add_argument('--out',default='docs/avatars/increment1');p.add_argument('--before',default='1c964dc');p.add_argument('--kinds',default='cat,plant');p.add_argument('--no-prototypes',action='store_true');a=p.parse_args();kinds=a.kinds.split(',')
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)

def module(folder,prefix):
 env=Environment(loader=FileSystemLoader(folder),autoescape=True,undefined=StrictUndefined)
 ids=count(1);families={x['key']:x['family'] for x in CATALOG}
 env.globals.update(avatar_uid=lambda:prefix+str(next(ids)),avatar_month=lambda:0,avatar_outfit=lambda:'default',
   avatar_family=lambda k:families[k],avatar_is_swimmer=lambda k:k in {'fish','dolphin'},
   avatar_care_verb=lambda k:'water' if families[k]=='plant' else 'feed')
 return env.get_template('_avatars.html').module

def prototypes(page):
 page.locator('.av-anchor-neck').evaluate_all('''els=>els.forEach(el=>{el.innerHTML='<path d="M-13-3Q0 4 13-3L0 15Z" fill="#588c9b" stroke="#355a70" stroke-width="1.2"/><path d="M-6 0L0 9" fill="none" stroke="#b7dcce"/>'})''')
 page.locator('.av-anchor-pot').evaluate_all('''els=>els.forEach(el=>{el.innerHTML='<path d="M-21-2Q0 4 21-2L19 10Q0 16-19 10Z" fill="#588c9b" stroke="#355a70" stroke-width="1"/><path d="M-15 4Q0 9 15 4" fill="none" stroke="#b7dcce" stroke-width="2"/>'})''')

with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
 # Load the complete historical macro tree; split species import shared helpers.
 for name in subprocess.check_output(['git','ls-tree','-r','--name-only',a.before,'templates'],text=True).splitlines():
  if Path(name).name.startswith('_avatar') or '/_avatar_species/' in name:
   target=Path(tmp)/Path(name).relative_to('templates');target.parent.mkdir(parents=True,exist_ok=True)
   target.write_bytes(subprocess.check_output(['git','show',a.before+':'+name]))
 before=module(tmp,'before-');after=module(ROOT/'templates','slice-')
 browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
 for theme in ['light','dark','contrast']:
  cards=[]
  for size in [64,170]:
   for kind in kinds:
    for label,macros in [('Before',before),('After',after)]:
     for stage in range(1,7):
      cards.append(f'<article><p>{label} {kind} {stage} · {size}px</p>'+str(macros.avatar(kind,stage,size=size,mood='okay'))+'</article>')
  html='<html><meta charset="utf-8"><title>Companion illustration comparison</title>'+str(after.avatar_defs())+f'<style>body{{margin:24px;font:14px system-ui;background:{"#182234" if theme=="dark" else "#fff"};color:{"#fff" if theme=="dark" else "#27232b"}}}main{{display:grid;grid-template-columns:repeat(6,1fr);gap:16px}}article{{padding:12px;border:1px solid #8886;border-radius:12px}}p{{font-size:12px}}</style><main>'+''.join(cards)+'</main></html>'
  html=re.sub(r'<script\b[^>]*>.*?</script>','',html,flags=re.S)
  context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
  page=context.new_page();page.set_content(html)
  ids=page.locator('[id]').evaluate_all('(els)=>els.map(e=>e.id)');assert len(ids)==len(set(ids))
  # Gallery-only prototypes attach to the actual per-stage owning groups.
  page.screenshot(path=str(out/f'before-after-bare-{theme}.png'),full_page=True)
  if not a.no_prototypes:prototypes(page)
  if not a.no_prototypes:page.screenshot(path=str(out/f'before-after-{theme}.png'),full_page=True)
  (out/f'gallery-{theme}.html').write_text(page.content());context.close()
 # Recording uses actual scripts through a local HTTP fixture origin.
 context=browser.new_context(viewport={'width':1440,'height':600},record_video_dir=str(out/'motion'))
 page=context.new_page()
 def serve(route):
  path=route.request.url.split('http://avatar.local')[-1].split('?')[0]
  if path.startswith('/static/'):
   route.fulfill(body=(ROOT/path.lstrip('/')).read_bytes(),content_type='text/javascript')
  elif path=='/avatar/care':route.fulfill(json={'ok':True,'mood':'happy','counted':False})
  else:
   cards=''.join('<article><p>'+label+' '+kind+'</p>'+str(m.avatar(kind,6,size=170,interactive=True,care=True,mood='okay'))+'</article>' for label,m in [('Before',before),('After',after)] for kind in kinds)
   route.fulfill(body='<html><meta charset="utf-8">'+str(after.avatar_defs())+'<style>body{font:16px system-ui;background:#f4f6fa}main{display:flex;gap:40px}</style><main>'+cards+'</main></html>',content_type='text/html')
 page.route('http://avatar.local/**',serve)
 page.add_init_script("const D=Date;window.Date=class extends D{constructor(...a){super(...(a.length?a:['2026-07-15T12:00:00Z']))}static now(){return D.now()}}")
 page.goto('http://avatar.local/');page.wait_for_timeout(2500)
 if not a.no_prototypes:prototypes(page)
 for selector in ['.av-play-btn','.av-care-btn']:
  for button in page.locator(selector).all():button.click(force=True)
  page.wait_for_timeout(2000)
 video=page.video
 context.close()
 Path(video.path()).replace(out/'before-after-motion.webm')
 browser.close()
print('Three before/after sheets, gallery accessory prototypes and motion recording written')
