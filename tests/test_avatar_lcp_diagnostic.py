"""Opt-in matched cold-load diagnostic; supplements, never replaces, 30s runs."""
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess

import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in local performance diagnostic')


def test_matched_cold_load_diagnostic(baseline_server, app_mod, tmp_path):
    from jinja2 import ChoiceLoader, FileSystemLoader
    from playwright.sync_api import sync_playwright
    origin,cookie,uid=baseline_server
    if os.getenv('CSS_AVATAR_DIAG_MOOD')=='happy':
        import storage as st
        conn=st.connect(app_mod.DB);st.record_avatar_care(conn,uid);conn.close()
    env=app_mod.templates.env;original_loader=env.loader
    loaders={'current':original_loader}
    for name,commit in [('increment0','1c964dc'),('increment1','10a7d0d')]:
        folder=tmp_path/name;folder.mkdir()
        for file in ['_avatars.html','_avatars_art.html']:
            (folder/file).write_bytes(subprocess.check_output(['git','show',commit+':templates/'+file]))
        loaders[name]=ChoiceLoader([FileSystemLoader(folder),original_loader])
    if os.getenv('CSS_AVATAR_DIAG_PROMOTION')=='1':
        for version in ['current','promoted']:
            folder=tmp_path/version;folder.mkdir()
            for file in ['_avatars.html','_avatars_art.html']:
                source=Path('templates',file).read_text()
                if version=='promoted' and file=='_avatars.html':
                    source=source.replace('</style>', '.avwrap[data-interactive] svg[data-avatar-art="v2"]{will-change:transform}</style>',1)
                (folder/file).write_text(source)
            loaders[version]=ChoiceLoader([FileSystemLoader(folder),original_loader])
    rows=[];svg_markup={}
    try:
        env.cache.clear()
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
            assert browser.version=='154.0.8037.57'
            for run in range(5):
                order=list(loaders) if run%2==0 else list(reversed(loaders))
                for version in order:
                    env.loader=loaders[version]
                    context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC',service_workers='block')
                    context.add_cookies([cookie]);context.add_init_script(PROBE)
                    context.add_init_script("new PerformanceObserver(l=>{const e=l.getEntries().at(-1);window.lcpCandidate={tag:e.element?.tagName,id:e.element?.id,text:e.element?.textContent?.slice(0,100),url:e.url,size:e.size}}).observe({type:'largest-contentful-paint',buffered:true})")
                    page=context.new_page();response=page.goto(origin+'/?view=me');page.wait_for_timeout(2000)
                    row=page.evaluate("()=>({lcp_ms:avatarProbe.lcp,candidate:window.lcpCandidate,navigation:performance.getEntriesByType('navigation')[0].toJSON(),mood:document.querySelector('.avwrap').dataset.mood,svg_will_change:getComputedStyle(document.querySelector('.avwrap svg')).willChange,svg_count:document.querySelectorAll('svg[data-avatar-kind]').length})")
                    svg=re.search(r'<svg\b[^>]*data-avatar-kind="cat"[^>]*>.*?</svg>',response.text(),re.S)[0]
                    svg_markup[version]=re.sub(r'av-[0-9a-f]{32}', 'av-LOCAL',svg)
                    rows.append(dict(version=version,run=run,**row));context.close()
            browser.close()
        same=svg_markup['increment1']==svg_markup['current']
        assert same,'Current Home cat SVG unexpectedly differs from increment 1'
        output=Path(os.getenv('CSS_AVATAR_OUT','docs/avatars/increment2a/application')).parent
        result={'diagnostic_only':True,'fixture_mood':os.getenv('CSS_AVATAR_DIAG_MOOD','default'),'promotion_variant':os.getenv('CSS_AVATAR_DIAG_PROMOTION')=='1','method':'Five cold contexts per art version, counterbalanced order, same actual Home route/cookie/CPU1/browser; 2s observation only, diagnostic not full-duration acceptance; loader-specific Jinja caches retained across rounds',
                'current_home_cat_svg_identical_to_increment1':same,
                'groups':[{ 'version':v,'lcp_median_ms':statistics.median(r['lcp_ms'] for r in rows if r['version']==v),'lcp_worst_ms':max(r['lcp_ms'] for r in rows if r['version']==v)} for v in loaders], 'samples':rows}
        (output/'cold-lcp-diagnostic.json').write_text(json.dumps(result,indent=2))
    finally:
        env.loader=original_loader;env.cache.clear()
