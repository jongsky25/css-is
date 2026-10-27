"""Exact paint/geometry gate for shared cat gradients; no memory measurement."""
import argparse
import ast
import gzip
import hashlib
from html.parser import HTMLParser
from itertools import count
import json
from pathlib import Path
import re
import subprocess
from jinja2 import Environment, DictLoader, StrictUndefined
from playwright.sync_api import sync_playwright
from scripts.avatar_baseline.visual_state import SNAPSHOT, compare

ROOT = Path(__file__).resolve().parents[2]
CURRENT = 'cf363bfe547d5e23619eee28cdaf68bd4b6d7753'
ORIGINAL = '1c964dcba2fa19de1eab077b00e0e5748d742554'
CANDIDATE = 'cd94bf3'


def module(ref, outfit):
    files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', ref, 'templates'], cwd=ROOT, text=True).splitlines()
    source = {n.removeprefix('templates/'): subprocess.check_output(['git', 'show', ref+':'+n], cwd=ROOT).decode() for n in files if '_avatar' in n}
    env = Environment(loader=DictLoader(source), autoescape=True, undefined=StrictUndefined)
    catalog = next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'storage.py').read_text()).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'AVATAR_CATALOG' for t in n.targets))
    families = {c['key']:c['family'] for c in catalog}
    ids = count(1)
    month = 12 if outfit == 'christmas' else 10 if outfit.startswith('halloween') else 0
    env.globals.update(avatar_uid=lambda:'fixture-'+str(next(ids)), avatar_family=lambda k:families[k], avatar_is_swimmer=lambda k:k in ['fish','dolphin'], avatar_month=lambda:month, avatar_outfit=lambda:outfit, avatar_care_verb=lambda k:'water' if families[k]=='plant' else 'feed')
    return env.get_template('_avatars.html').module, catalog, month


def normalize(state):
    # Only deliberate cat definition removal and gradient reference renaming.
    # IDs/references are independently checked against the unmodified document.
    text = json.dumps(state)
    text = re.sub(r'fixture-\d+-(fur|cream)', r'avg-cat-v2-\1', text)
    text = re.sub(r'fixture-\d+-', 'fixture-', text)
    result = json.loads(text)
    for i, row in enumerate(result):
        row['index'] = i
    return result


class Inventory(HTMLParser):
    def __init__(self):
        super().__init__(); self.elements=0; self.attributes=0; self.signatures=set(); self.bytes=0
    def handle_starttag(self, tag, attrs):
        self.elements += 1; self.attributes += len(attrs)
        self.signatures.add(tuple(attrs)); self.bytes += sum(len(k.encode())+len((v or '').encode()) for k,v in attrs)
    handle_startendtag = handle_starttag
    def result(self):
        return {'elements':self.elements, 'attributes':self.attributes, 'distinct_attribute_vectors':len(self.signatures), 'attribute_utf8_bytes':self.bytes}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--browser',required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    refs={k:subprocess.check_output(['git','rev-parse',v],cwd=ROOT,text=True).strip() for k,v in [('original',ORIGINAL),('current',CURRENT),('candidate',CANDIDATE)]}
    inventories={}
    for arm,ref in refs.items():
        m,_,_=module(ref,'default'); inv=Inventory()
        for _ in range(6): inv.feed(str(m.avatar_svg('cat',1,0,'default')))
        inventories[arm]=inv.result()
    (a.out/'inventory.json').write_text(json.dumps(inventories,indent=2))
    modules={o:{arm:module(ref,o) for arm,ref in refs.items() if arm!='original'} for o in ['default','halloween','halloween_vampire','halloween_pumpkin','christmas']}
    rows=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=a.browser,args=['--no-sandbox']);assert browser.version=='156.0.8078.47'
        for theme,bg in [('light','#f4f6fa'),('dark','#162032'),('contrast','#fff')]:
            for outfit,arms in modules.items():
                for static in [False,True]:
                    case=f'{theme}-{outfit}-'+('preview' if static else 'live')
                    states=[];pictures=[];checks=[]
                    for arm,(m,catalog,month) in arms.items():
                        cards=[]
                        for c in catalog:
                            for stage in range(1,7):
                                art=m.avatar_svg(c['key'],stage,month,outfit,static_preview=True) if static else m.avatar(c['key'],stage,name='',size=64,interactive=True)
                                cards.append('<div class="avcard">'+str(art)+'</div>')
                        defs=re.sub(r'<script\b[^>]*>.*?</script>','',str(m.avatar_defs()),flags=re.S)
                        html=f'<html><meta charset="utf-8"><style>body{{margin:0;background:{bg};--accent:#547bb5}}main{{display:grid;grid-template-columns:repeat(12,80px)}}.avcard{{width:80px;height:96px;display:grid;place-items:center}}.avcard svg{{width:64px;height:75px;will-change:transform}}</style>{defs}<main>'+''.join(cards)+'</main></html>'
                        context=browser.new_context(viewport={'width':960,'height':768});page=context.new_page();page.set_content(html)
                        page.evaluate('''async()=>{const aa=document.getAnimations();aa.forEach(a=>a.pause());await Promise.all(aa.map(a=>a.ready));aa.forEach(a=>a.currentTime=0);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));if(aa.some(a=>a.currentTime!==0||a.playState!=='paused'))throw Error('freeze');}''')
                        check=page.evaluate('''()=>{const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);const missing=[...document.querySelectorAll('[fill]')].map(e=>e.getAttribute('fill')).filter(v=>v.startsWith('url(#')).filter(v=>!document.getElementById(v.slice(5,-1)));return {ids_unique:new Set(ids).size===ids.length,missing,avatars:document.querySelectorAll('svg[data-avatar-kind]').length,cat_v2:document.querySelectorAll('svg[data-avatar-kind="cat"][data-avatar-art="v2"]').length}}''')
                        assert check=={'ids_unique':True,'missing':[],'avatars':96,'cat_v2':6};checks.append(check)
                        raw=page.evaluate('('+SNAPSHOT+')()')
                        # Strip only nonpainting cat defs from the state comparison.
                        indices=page.evaluate('''()=>[...document.querySelectorAll('main,main *')].map((e,i)=>[e,i]).filter(([e])=>e.closest('svg[data-avatar-kind="cat"] defs')).map(([,i])=>i)''')
                        state=normalize([s for i,s in enumerate(raw) if i not in indices]);states.append(state)
                        shot=page.screenshot(caret='initial');repeat=page.screenshot(caret='initial');assert shot==repeat,'Unstable same-document pixels'
                        assert raw==page.evaluate('('+SNAPSHOT+')()'),'Screenshot mutated state'
                        pictures.append(shot);(a.out/f'{case}-{arm}.png').write_bytes(shot)
                        with gzip.open(a.out/f'{case}-{arm}.json.gz','wt') as f:json.dump(raw,f)
                        context.close()
                    comparison=compare(*states)
                    row={'case':case,'cells':96,'pixel_identical':pictures[0]==pictures[1],'state_comparison':comparison,'checks':checks}
                    rows.append(row);(a.out/'progress.json').write_text(json.dumps(rows,indent=2))
        browser.close()
    assessment={'acceptance':False,'refs':refs,'browser':'156.0.8078.47','sheets':rows,'cells':len(rows)*96,'all_pixels_identical':all(r['pixel_identical'] for r in rows),'all_states_identical':all(r['state_comparison']['identical'] for r in rows),'normalization':'Cat nonpainting defs excluded; scoped gradient IDs and equivalent references normalized. Other attributes, paint styles, geometry and transforms compare exactly. Unique IDs and resolved references checked before normalization. Isolated-paint fixture; no memory claim.'}
    (a.out/'assessment.json').write_text(json.dumps(assessment,indent=2));print(json.dumps({k:v for k,v in assessment.items() if k!='sheets'}))
    assert assessment['all_pixels_identical'] and assessment['all_states_identical']


if __name__=='__main__':main()
