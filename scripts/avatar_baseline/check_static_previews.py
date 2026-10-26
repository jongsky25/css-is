"""Compare decorative SVG geometry under identical, uncomposited static painting.

Full SVG's movement hint rasterizes into a separate layer and changes edge
antialiasing. Disable that hint in the reference to isolate removed content.
The live SVG contract is checked separately by check_lazy_equivalence.py.
"""
import argparse
from hashlib import sha256
from io import BytesIO
from itertools import count
import json
from pathlib import Path
import re
import shutil
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from gallery import ROOT, CATALOG

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
rows=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
 for theme,background in [('light','#f4f6fa'),('dark','#162032'),('contrast','#fff')]:
  for month,outfit in [(m,'default') for m in range(13)]+[(10,c) for c in ['halloween','halloween_vampire','halloween_pumpkin']]+[(12,'christmas')]:
   images=[];nodes=[]
   for reduced in [False,True]:
    env=Environment(loader=FileSystemLoader(ROOT/'templates'),autoescape=True,undefined=StrictUndefined)
    ids=count(1);families={c['key']:c['family'] for c in CATALOG}
    env.globals.update(avatar_uid=lambda:'static-check-'+str(next(ids)),avatar_family=lambda k:families[k],avatar_is_swimmer=lambda k:k in ['fish','dolphin'],avatar_month=lambda:month,avatar_outfit=lambda:outfit)
    macro=env.get_template('_avatars.html').module
    body=''.join('<div class="avcard">'+str(macro.avatar_svg(c['key'],stage,month,outfit,static_preview=reduced))+'</div>' for c in CATALOG for stage in range(1,7))
    defs=re.sub(r'<script\b[^>]*>.*?</script>','',str(macro.avatar_defs()),flags=re.S)
    html=f'<html><style>body{{margin:0;background:{background}}}main{{display:grid;grid-template-columns:repeat(12,80px)}}.avcard{{width:80px;height:96px;display:grid;place-items:center}}.avcard svg{{width:64px;height:75px}}</style>{defs}<main>{body}</main></html>'
    context=browser.new_context(viewport={'width':960,'height':768},reduced_motion='reduce')
    page=context.new_page();page.set_content(html)
    if not reduced:
     page.add_style_tag(content='.avcard .avmove {will-change:auto}')
    assert page.locator('svg[data-avatar-kind]').count()==96
    nodes.append(page.locator('*').count());images.append(page.screenshot())
    context.close()
   diff=ImageChops.difference(Image.open(BytesIO(images[0])).convert('RGB'),Image.open(BytesIO(images[1])).convert('RGB'))
   name=f'{theme}-{outfit}-{month:02}.png';(a.out/name).write_bytes(images[1])
   row={'file':name,'cells':96,'pixel_identical':diff.getbbox() is None,'full_nodes':nodes[0],'preview_nodes':nodes[1],'reference_sha256':sha256(images[0]).hexdigest(),'preview_sha256':sha256(images[1]).hexdigest()};rows.append(row)
   if not row['pixel_identical']:(a.out/('reference-'+name)).write_bytes(images[0])
 browser.close()
(a.out/'assessment.json').write_text(json.dumps({'browser':browser.version,'reference_paint_mode':'Full SVG with static movement will-change disabled; original composited pixels differ and are retained separately.','cells':len(rows)*96,'all_pixel_identical':all(r['pixel_identical'] for r in rows),'sheets':rows},indent=2))
assert all(r['pixel_identical'] for r in rows), 'Static preview pixels changed; evidence retained'
print(f'{len(rows)*96} pixel-identical cells; {rows[0]["full_nodes"]-rows[0]["preview_nodes"]} fewer DOM nodes per 96-cell sheet')
