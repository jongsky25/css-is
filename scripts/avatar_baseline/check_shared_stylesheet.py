"""Exact stylesheet extraction and same-browser pixel comparison; no memory claims."""
import argparse
import ast
from hashlib import sha256
from io import BytesIO
from itertools import count
import json
from pathlib import Path
import re
import shutil
import subprocess
from jinja2 import Environment, DictLoader, FileSystemLoader, StrictUndefined
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from scripts.avatar_baseline.visual_state import SNAPSHOT, compare


def main():
    p=argparse.ArgumentParser();p.add_argument('--case');p.add_argument('--isolate-avatar-paint',action='store_true');p.add_argument('--raster-threads',type=int,choices=[1]);p.add_argument('--diagnose',action='store_true');p.add_argument('--previews-only',action='store_true');p.add_argument('--same-document',action='store_true');p.add_argument('--software-rendering',action='store_true');p.add_argument('--same-source-control',action='store_true');p.add_argument('--candidate',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.same_document and a.same_source_control:
        p.error('--same-document and --same-source-control are separate experiments')
    root=Path(__file__).resolve().parents[2];a.out.mkdir(parents=True,exist_ok=False)
    old=subprocess.check_output(['git','show','f700187:templates/_avatars.html'],cwd=root).decode()
    new=(a.candidate/'templates/_avatars.html').read_text();css=(a.candidate/'static/css/avatars.css').read_text()
    link='<link rel="stylesheet" href="/static/css/avatars.css?v=1">'
    assert new.count(link)==1 and new.replace(link,'<style>'+css+'</style>')==old
    files=subprocess.check_output(['git','ls-tree','-r','--name-only','f700187','templates'],cwd=root,text=True).splitlines()
    reference={n.removeprefix('templates/'):subprocess.check_output(['git','show','f700187:'+n],cwd=root).decode() for n in files if '_avatar' in n}
    catalog=next(ast.literal_eval(n.value) for n in ast.parse((root/'storage.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='AVATAR_CATALOG' for t in n.targets))
    families={c['key']:c['family'] for c in catalog};rows=[]
    def render(candidate,theme,outfit,static):
        env=Environment(loader=FileSystemLoader(a.candidate/'templates') if candidate else DictLoader(reference),autoescape=True,undefined=StrictUndefined)
        ids=count(1);month=12 if outfit=='christmas' else 10 if outfit.startswith('halloween') else 0
        env.globals.update(avatar_care_verb=lambda k:'water' if families[k]=='plant' else 'feed',avatar_uid=lambda:'stylesheet-'+str(next(ids)),avatar_family=lambda k:families[k],avatar_is_swimmer=lambda k:k in ['fish','dolphin'],avatar_month=lambda:month,avatar_outfit=lambda:outfit)
        m=env.get_template('_avatars.html').module
        cards=[]
        for c in catalog:
            for stage in range(1,7):
                svg=m.avatar_svg(c['key'],stage,month,outfit,static_preview=True) if static else m.avatar(c['key'],stage,name='',size=64,interactive=True)
                cards.append('<div class="avcard">'+str(svg)+'</div>')
        defs=re.sub(r'<script\b[^>]*>.*?</script>','',str(m.avatar_defs()),flags=re.S)
        if a.isolate_avatar_paint:defs += '<style>.avcard svg {will-change:transform}</style>'
        bg={'light':'#f4f6fa','dark':'#162032','contrast':'#fff'}[theme]
        return f'<html><meta charset="utf-8"><style>body{{margin:0;background:{bg};--accent:#547bb5}} main{{display:grid;grid-template-columns:repeat(12,80px)}}.avcard{{width:80px;height:96px;display:grid;place-items:center}}.avcard svg{{width:64px;height:75px}}</style>{defs}<main>'+''.join(cards)+'</main></html>'
    def freeze(page):
        page.evaluate('''async () => {
                            const animations = document.getAnimations();
                            animations.forEach(a => a.pause());
                            await Promise.all(animations.map(a => a.ready));
                            animations.forEach(a => {a.currentTime = 0});
                            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                            if (animations.some(a => a.currentTime !== 0 || a.playState !== 'paused'))
                                throw new Error('Animation freeze incomplete');
                        }''')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox']+(['--disable-gpu'] if a.software_rendering else [])+(['--num-raster-threads='+str(a.raster_threads)] if a.raster_threads else []))
        assert browser.version=='156.0.8078.47'
        for theme in ['light','dark','contrast']:
            for outfit in ['default','halloween','halloween_vampire','halloween_pumpkin','christmas']:
                for static in ([True] if a.previews_only else [False,True]):
                    case=f'{theme}-{outfit}-{"preview" if static else "live"}'
                    if a.case and case!=a.case:continue
                    images=[];rules=[];states=[];within=[];layers=[]
                    for candidate in [False,True]:
                        effective_candidate=candidate and not a.same_source_control
                        html=render(effective_candidate,theme,outfit,static)
                        if not (a.same_document and candidate):
                            context=browser.new_context(viewport={'width':960,'height':768})
                            def route(r):
                                if '/static/css/avatars.css' in r.request.url:r.fulfill(body=css,content_type='text/css')
                                else:r.fulfill(body=html,content_type='text/html')
                            context.route('http://avatar.test/**',route)
                            page=context.new_page();page.goto('http://avatar.test/sheet',wait_until='load')
                        else:
                            page.evaluate("""async () => {
                                const old = document.querySelectorAll('style')[1];
                                window.originalAvatarStyle = old;
                                const link = document.createElement('link');
                                link.rel = 'stylesheet'; link.href = '/static/css/avatars.css?v=1';
                                const loaded = new Promise((resolve, reject) => {
                                    link.onload = resolve; link.onerror = reject;
                                });
                                old.before(link); await loaded; old.remove();
                            }""")
                        cdp=context.new_cdp_session(page);layer_events=[]
                        cdp.on('LayerTree.layerTreeDidChange',lambda e:layer_events.append(e))
                        cdp.send('LayerTree.enable')
                        assert page.locator('svg[data-avatar-kind]').count()==96
                        if effective_candidate:assert page.locator('link[href="/static/css/avatars.css?v=1"]').evaluate('e=>e.sheet.cssRules.length')>100
                        freeze(page)
                        rules.append(page.evaluate('Array.from(document.styleSheets).flatMap(s=>Array.from(s.cssRules,r=>r.cssText))'))
                        if a.diagnose:states.append(json.loads(page.evaluate('JSON.stringify(('+SNAPSHOT+')())')))
                        capture=page.screenshot(); repeat=page.screenshot()
                        if a.diagnose:within.append(compare(states[-1],json.loads(page.evaluate('JSON.stringify(('+SNAPSHOT+')())'))))
                        assert capture==repeat, 'Same-document screenshot unstable'
                        tree=layer_events[-1].get('layers',[]) if layer_events else []
                        reasons=[]
                        for layer in tree:
                            if layer.get('drawsContent') and len(reasons)<3:
                                reasons.append(cdp.send('LayerTree.compositingReasons',{'layerId':layer['layerId']}))
                        layers.append({'count':len(tree),'draws_content':sum(bool(l.get('drawsContent')) for l in tree),'sample_reasons':reasons})
                        cdp.detach()
                        images.append(capture)
                        if a.same_document and candidate:
                            page.evaluate("""() => { const link=document.querySelector('link[href="/static/css/avatars.css?v=1"]'); link.before(window.originalAvatarStyle); getComputedStyle(document.body).display; link.remove(); }""")
                            freeze(page)
                            restored=page.screenshot()
                            if restored!=images[0]:
                                (a.out/'before-restore.png').write_bytes(images[0]);(a.out/'restored.png').write_bytes(restored)
                                (a.out/'external.png').write_bytes(images[1])
                            assert restored==images[0], 'Inline restoration changes pixels'
                        if not a.same_document or candidate:context.close()
                    assert rules[0]==rules[1], 'CSSOM rules differ'
                    difference=ImageChops.difference(Image.open(BytesIO(images[0])).convert('RGB'),Image.open(BytesIO(images[1])).convert('RGB'))
                    name=f'{theme}-{outfit}-{"preview" if static else "live"}.png';(a.out/name).write_bytes(images[1])
                    identical=difference.getbbox() is None
                    rows.append({'file':name,'cells':96,'pixel_identical':identical,'cssom_identical':True,'layers':layers,'reference_sha256':sha256(images[0]).hexdigest(),'candidate_sha256':sha256(images[1]).hexdigest()})
                    if a.diagnose:
                        rows[-1]['state_comparison']=compare(*states)
                        rows[-1]['within_document_state_comparisons']=within
                    if not identical:(a.out/('reference-'+name)).write_bytes(images[0])
                    (a.out/'progress.json').write_text(json.dumps(rows,indent=2)+'\n')
        browser.close()
    result={'all_states_identical':all(r['state_comparison']['identical'] and all(c['identical'] for c in r['within_document_state_comparisons']) for r in rows) if a.diagnose else None,'isolate_avatar_paint':a.isolate_avatar_paint,'raster_threads':a.raster_threads,'same_document':a.same_document,'software_rendering':a.software_rendering,'same_source_control':a.same_source_control,'acceptance':False,'browser':'156.0.8078.47','stylesheet_bytes':len(css.encode()),'stylesheet_sha256':sha256(css.encode()).hexdigest(),'template_reconstructed_exactly':True,'all_pixels_identical':all(r['pixel_identical'] for r in rows),'cells':len(rows)*96,'sheets':rows,'limits':'Routed fixture only for visual comparison; not cache or memory evidence. Animation pause readiness awaited, time zero applied, two rendering frames awaited, and repeated same-document screenshots identical in both versions. Original artwork/runtime unchanged.'}
    (a.out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='sheets'}))
    assert result['all_pixels_identical']
    if a.diagnose:assert result['all_states_identical'], 'DOM/style/geometry differs'


if __name__=='__main__':main()
