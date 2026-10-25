"""Check positional rigs and frozen care/mood frames through real SVG/CSS macros."""
import argparse
import json
import re
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
from gallery import render

p=argparse.ArgumentParser();p.add_argument('--out',default='docs/avatars/increment2a');a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True);rows=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
    for theme in ['light','dark','contrast']:
        context=browser.new_context(viewport={'width':1440,'height':1000})
        page=context.new_page();page.set_content(re.sub(r'<script\b[^>]*>.*?</script>','',render('gallery',theme),flags=re.S))
        page.locator('article').evaluate_all("els=>els.forEach(e=>{if(!['cactus','bonsai','sunflower'].includes(e.querySelector('svg').dataset.avatarKind))e.remove()})")
        for phase in ['bloom','water']:
            page.locator('.avwrap').evaluate_all("(els,phase)=>els.forEach(e=>{e.classList.remove('av-do-bloom','av-caring-water');e.classList.add(phase==='bloom'?'av-do-bloom':'av-caring-water')})",phase)
            page.evaluate("()=>document.getAnimations().forEach(a=>{a.pause();a.currentTime=1200})")
            data=page.locator('.avwrap').evaluate_all('''els=>els.map(e=>{const svg=e.querySelector('svg'),b=svg.getBoundingClientRect();return {kind:e.dataset.kind,stage:svg.dataset.avatarStage,mood:e.dataset.mood,filter:getComputedStyle(svg).filter,soil_opacity:Number(getComputedStyle(e.querySelector('.av-soilwet')).opacity),blooms:[...e.querySelectorAll('.av-bloom')].map(g=>{const r=g.getBoundingClientRect();return {cx:(r.x+r.width/2-b.x)/b.width,cy:(r.y+r.height/2-b.y)/b.height}})}})''')
            assert len(data)==54
            for row in data:
                assert row['filter']=='none',row
                for bloom in row['blooms']:
                    assert 0<=bloom['cx']<=1 and 0<=bloom['cy']<=1,(theme,phase,row)
                if phase=='water':assert row['soil_opacity']>.5,row
                rows.append(dict(theme=theme,phase=phase,**row))
            page.screenshot(path=str(out/f'{phase}-moods-{theme}.png'),full_page=True)
        context.close()
    browser.close()
(out/'motion-rig-check.json').write_text(json.dumps({'cases':len(rows),'method':'Actual macros/CSS; bloom-turn and watering animations paused at 1200ms; SVG bloom centers remain inside viewBox, wet soil visible; no behavior JS in static sheet','results':rows},indent=2))
print(len(rows),'stage/mood/theme/reaction cases passed')
