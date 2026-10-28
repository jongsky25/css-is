"""Actual-macro contact sheets for final base art and compatible equipment."""
import argparse
import json
import re
import shutil
from itertools import count
from pathlib import Path
import sys
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from playwright.sync_api import sync_playwright
from gallery import CATALOG, ROOT
sys.path.insert(0,str(ROOT))
import companion_wardrobe as wardrobe

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
env=Environment(loader=FileSystemLoader(ROOT/'templates'),autoescape=True,undefined=StrictUndefined)
uids=count(1);families={x['key']:x['family'] for x in CATALOG}
env.globals.update(avatar_uid=lambda:'review-'+str(next(uids)),avatar_month=lambda:0,avatar_outfit=lambda:'default',avatar_family=lambda k:families[k],avatar_is_swimmer=lambda k:k in {'fish','dolphin'},avatar_equipment_catalog=wardrobe.CATALOG)
macro=env.get_template('_avatars.html').module
index=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
    for theme in ['light','dark','contrast']:
        for group in ['base','equipment']:
            cards=[]
            for species in CATALOG:
                kind=species['key']
                choices=[None] if group=='base' else [key for key,item in wardrobe.CATALOG.items() if kind in item['species']]
                for key in choices:
                    for stage in range(1,7) if group=='base' else [1,3,6]:
                        preferences=wardrobe.validate(kind,'none',[]) if key is None else wardrobe.validate(kind,'personal',[key])
                        art=str(macro.avatar_svg(kind,stage,static_preview=True,preferences=preferences))
                        cards.append('<article><p>'+kind+' · '+str(stage)+' · '+(key or 'base')+'</p><div class="art">'+art+'</div></article>')
            bg='#182234' if theme=='dark' else '#fff';fg='#fff' if theme=='dark' else '#27232b'
            html='<html><meta charset="utf-8">'+str(macro.avatar_defs())+f'<style>body{{background:{bg};color:{fg};font:12px system-ui;margin:12px}}main{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}article{{border:1px solid #8888;border-radius:10px;padding:10px;text-align:center}}p{{min-height:28px}}.art{{width:96px;height:112px;margin:auto}}</style><main>'+''.join(cards)+'</main></html>'
            html=re.sub(r'<script\b[^>]*>.*?</script>','',html,flags=re.S)
            context=browser.new_context(viewport={'width':1100,'height':900},reduced_motion='reduce',forced_colors='active' if theme=='contrast' else 'none')
            page=context.new_page();page.set_content(html)
            ids=page.locator('[id]').evaluate_all('(es)=>es.map(e=>e.id)');assert len(ids)==len(set(ids))
            assert page.locator('svg[data-avatar-kind]').count()==len(cards)
            file=group+'-'+theme+'.png';page.screenshot(path=str(a.out/file),full_page=True)
            index.append({'file':file,'theme':theme,'cards':len(cards),'art_size_px':96,'forced_colors':theme=='contrast'})
            context.close()
    browser.close()
(a.out/'index.json').write_text(json.dumps(index,indent=2)+'\n')
print(json.dumps(index))
