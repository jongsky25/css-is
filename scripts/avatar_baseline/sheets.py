"""Render 96-cell, 64px sheets for every month/costume and surface.

Run after timing measurements, not concurrently. Uses only the real Jinja macros.
"""
import argparse
import json
from pathlib import Path
import shutil
from playwright.sync_api import sync_playwright
from gallery import render

p=argparse.ArgumentParser();p.add_argument('--out',default='docs/avatars/sheets');a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
index=[]
boxes=[]
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
 for theme in ['light','dark','contrast']:
  for outfit, month in [('default',m) for m in range(13)]+[(o,m) for o,m in [('halloween',10),('halloween_vampire',10),('halloween_pumpkin',10),('christmas',12)]]:
   c=b.new_context(viewport={'width':960,'height':900},reduced_motion='reduce',timezone_id='UTC')
   page=c.new_page();page.clock.set_fixed_time('2026-07-15T12:00:00Z')
   # Static visual fixture: suppress the script tags, retain actual macro CSS/SVG.
   import re
   html=re.sub(r'<script\b[^>]*>.*?</script>','',render('sheet',theme,outfit,month),flags=re.S)
   page.set_content(html)
   assert page.locator('svg[data-avatar-kind]').count()==96
   if theme=='light' and outfit=='default' and month==0:
    boxes=[page.locator('article').nth(row*6+5).bounding_box() for row in range(16)]
   ids=page.locator('[id]').evaluate_all('(es)=>es.map(e=>e.id)')
   assert len(ids)==len(set(ids)), 'Duplicate SVG IDs'
   file=f'{theme}-{outfit}-{month:02}.png'
   page.screenshot(path=str(out/file),full_page=True)
   index.append({'file':file,'theme':theme,'outfit':outfit,'month':month,'cells':96,'art_size_px':64})
   c.close()
 b.close()
(out/'index.json').write_text(json.dumps(index,indent=2))
print(f'{len(index)} sheets, {len(index)*96} base/stage/outfit/surface combinations')

# Monthly overview preserves 64px stage-6 artwork for all 16 species.
from PIL import Image, ImageDraw
canvas=Image.new('RGB',(12*140,16*140+35),'#f4f6fa');draw=ImageDraw.Draw(canvas)
for month in range(1,13):
 im=Image.open(out/f'light-default-{month:02}.png')
 draw.text(((month-1)*140+8,8),f'Month {month}',fill='black')
 for row,box in enumerate(boxes):
  x,y,w,h=[box[k] for k in ['x','y','width','height']]
  canvas.paste(im.crop((int(x),int(y),int(x+w),int(y+h))),((month-1)*140,row*140+35))
canvas.save(out/'monthly-stage6-overview.png')
