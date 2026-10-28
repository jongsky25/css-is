"""Before/after synthetic motion recording, each arm using its own CSS and JS."""
import argparse
from itertools import count
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit
from jinja2 import Environment,FileSystemLoader,StrictUndefined
from playwright.sync_api import sync_playwright
from gallery import ROOT
import sys
sys.path.insert(0,str(ROOT))
import companion_wardrobe as wardrobe

p=argparse.ArgumentParser();p.add_argument('--before',default='0a91f73');p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp,sync_playwright() as pw:
    folder=Path(tmp)
    for file in subprocess.check_output(['git','ls-tree','-r','--name-only',a.before,'templates'],text=True).splitlines():
        if Path(file).name.startswith('_avatar') or '/_avatar_species/' in file:
            path=folder/Path(file).relative_to('templates');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(subprocess.check_output(['git','show',a.before+':'+file]))
    browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
    for arm,templates in [('before',folder),('after',ROOT/'templates')]:
        env=Environment(loader=FileSystemLoader(templates),autoescape=True,undefined=StrictUndefined);ids=count(1)
        env.globals.update(avatar_uid=lambda:'motion-'+str(next(ids)),avatar_month=lambda:0,avatar_outfit=lambda:'default',avatar_family=lambda k:'plant' if k=='fern' else 'animal',avatar_is_swimmer=lambda k:k in {'fish','dolphin'},avatar_care_verb=lambda k:'water' if k=='fern' else 'feed',avatar_equipment_catalog=wardrobe.CATALOG)
        macros=env.get_template('_avatars.html').module
        cards=''.join('<article class="av-play"><p>'+arm+' · '+kind+'</p>'+str(macros.avatar(kind,6,name=kind,size=170,interactive=True,care=True,drag=True))+'</article>' for kind in ['fern','dog','bat','fish'])
        html='<html><meta charset="utf-8">'+str(macros.avatar_defs())+'<style>body{font:15px system-ui;background:#f4f6fa}main{display:grid;grid-template-columns:repeat(4,1fr);gap:20px}article{border:1px solid #aaa8;border-radius:16px;min-height:470px;text-align:center}</style><main>'+cards+'</main></html>'
        context=browser.new_context(viewport={'width':1200,'height':600},record_video_dir=str(a.out/'capture'),record_video_size={'width':1200,'height':600},timezone_id='UTC')
        context.add_init_script("const D=Date;window.Date=class extends D{constructor(...a){super(...(a.length?a:['2026-07-15T12:00:00Z']))}static now(){return D.now()}};let seed=12345;Math.random=()=>((seed=(1664525*seed+1013904223)>>>0)/4294967296)")
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def serve(route):
            path=urlsplit(route.request.url).path
            if path.startswith('/static/'):
                body=subprocess.check_output(['git','show',a.before+':'+path.lstrip('/')]) if arm=='before' else (ROOT/path.lstrip('/')).read_bytes()
                route.fulfill(body=body,content_type='text/javascript')
            elif path=='/avatar/care':route.fulfill(json={'ok':True,'counted':False,'mood':'happy'})
            else:route.fulfill(body=html,content_type='text/html')
        page.route('http://avatar.local/**',serve);page.goto('http://avatar.local/')
        page.wait_for_timeout(2500)
        for button in page.locator('.av-care-btn').all():button.click(force=True)
        page.wait_for_timeout(2200)
        for button in page.locator('.av-play-btn').all():button.click(force=True)
        page.wait_for_timeout(2200)
        video=page.video;context.close();Path(video.path()).replace(a.out/(arm+'-motion.webm'))
        assert not errors,errors
    browser.close()
print('Separate original/current runtime recordings written; synthetic care responses, no production data')
