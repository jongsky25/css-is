"""Check positional rigs and frozen care/mood frames through real SVG/CSS macros."""
import argparse
import json
import re
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
from gallery import render

p=argparse.ArgumentParser();p.add_argument('--out',default='docs/avatars/increment2a');p.add_argument('--kinds',default='cactus,bonsai,sunflower');p.add_argument('--phases',default='bloom,water');a=p.parse_args();kinds=a.kinds.split(',');phases=a.phases.split(',')
out=Path(a.out);out.mkdir(parents=True,exist_ok=True);rows=[];reduced_checks=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
    for theme in ['light','dark','contrast']:
        context=browser.new_context(viewport={'width':1440,'height':1000})
        page=context.new_page();page.set_content(re.sub(r'<script\b[^>]*>.*?</script>','',render('gallery',theme),flags=re.S))
        page.locator('article').evaluate_all("(els,kinds)=>els.forEach(e=>{if(!kinds.includes(e.querySelector('svg').dataset.avatarKind))e.remove()})",kinds)
        for phase in phases:
            page.locator('.avwrap').evaluate_all("(els,phase)=>els.forEach(e=>{e.classList.remove('av-do-bloom','av-caring-water','av-do-ripple','av-do-wobble','av-do-spore','av-do-plump','av-do-blink');e.classList.add(phase==='water'?'av-caring-water':'av-do-'+phase)})",phase)
            page.evaluate("(time)=>document.getAnimations().forEach(a=>{a.pause();a.currentTime=time})",1200 if phase=='water' else 120 if phase=='blink' else 450)
            data=page.locator('.avwrap').evaluate_all('''els=>els.map(e=>{const svg=e.querySelector('svg'),b=svg.getBoundingClientRect();return {kind:e.dataset.kind,stage:svg.dataset.avatarStage,mood:e.dataset.mood,filter:getComputedStyle(svg).filter,soil_opacity:Number(getComputedStyle(e.querySelector('.av-soilwet')).opacity),effects:[...svg.querySelectorAll('g,ellipse')].map(g=>getComputedStyle(g).animationName).filter(n=>n!=='none'),spore_opacity:e.querySelector('.av-spore')?Number(getComputedStyle(e.querySelector('.av-spore')).opacity):null,parts:[...e.querySelectorAll('.av-bloom,.av-cap,.av-spore,[class*="av-frond-"]')].map(g=>{const r=g.getBoundingClientRect();return {classes:g.getAttribute('class'),cx:(r.x+r.width/2-b.x)/b.width,cy:(r.y+r.height/2-b.y)/b.height}})}})''')
            applicable={'ripple':{'fern'},'wobble':{'mushroom'},'spore':{'mushroom'},'plump':{'succulent'},'blink':{'mushroom'},'bloom':set(kinds)-{'fern','mushroom'},'water':set(kinds)}[phase] & set(kinds)
            data=[row for row in data if row['kind'] in applicable]
            assert len(data)==len(applicable)*18
            for row in data:
                assert row['filter']=='none',row
                for part in row['parts']:
                    assert 0<=part['cx']<=1 and 0<=part['cy']<=1,(theme,phase,row)
                if phase=='water':
                    assert row['soil_opacity']>.5,row
                    if row['kind']=='fern':assert 'av-unfurl' in row['effects'],row
                if phase=='ripple':assert row['effects'].count('av-frondsway')==int(row['stage']),row
                if phase=='wobble':assert 'av-wobble' in row['effects'],row
                if phase=='spore':assert 'av-rise' in row['effects'] and row['spore_opacity']>.5,row
                if phase=='plump':assert 'av-plump' in row['effects'],row
                if phase=='blink' and int(row['stage'])>=2:assert row['effects'].count('av-blink')==2,row
                if phase=='bloom' and row['parts']:assert 'av-bloomturn' in row['effects'],row
                rows.append(dict(theme=theme,phase=phase,**row))
            page.screenshot(path=str(out/f'{phase}-moods-{theme}.png'),full_page=True)
            page.emulate_media(reduced_motion='reduce')
            remaining=page.locator('.avwrap svg *').evaluate_all("els=>els.map(e=>({tag:e.tagName,classes:e.getAttribute('class'),name:getComputedStyle(e).animationName})).filter(e=>e.name!=='none')")
            assert not remaining,(theme,phase,remaining)
            reduced_checks.append({'theme':theme,'phase':phase,'remaining_animations':len(remaining)})
            page.emulate_media(reduced_motion='no-preference')
        context.close()
    browser.close()
(out/'motion-rig-check.json').write_text(json.dumps({'cases':len(rows),'reduced_motion_checks':reduced_checks,'method':'Actual macros/CSS; bloom-turn and watering animations ripple/wobble/spore/plump/bloom paused at450ms, blink at120ms, watering at1200ms; relevant species only per phase; animated-part centers inside viewBox, expected CSS animation names and spore/wet-soil visibility checked; no behavior JS in static sheet','results':rows},indent=2))
print(len(rows),'stage/mood/theme/reaction cases passed')
