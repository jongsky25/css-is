"""Pixel-check the fourteen untouched species across all captured sheet variants."""
import argparse
import json
from pathlib import Path
import re
import shutil
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from gallery import CATALOG,render

p=argparse.ArgumentParser();p.add_argument('--before',default='docs/avatars/sheets');p.add_argument('--after',default='docs/avatars/increment1/sheets');p.add_argument('--changed',default='cat,plant');a=p.parse_args()
base=Path(a.before);current=Path(a.after);changed=set(a.changed.split(','));species=len(CATALOG)-len(changed)
index=json.loads((base/'index.json').read_text())
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':960,'height':900},reduced_motion='reduce')
    page.set_content(re.sub(r'<script\b[^>]*>.*?</script>','',render('sheet'),flags=re.S))
    boxes=[page.locator('article').nth(i).bounding_box() for i in range(96)]
    browser.close()
checked=0
for entry in index:
    old=Image.open(base/entry['file']).convert('RGB');new=Image.open(current/entry['file']).convert('RGB')
    assert old.size==new.size,entry['file']
    for row,item in enumerate(CATALOG):
        if item['key'] in changed:continue
        for stage in range(6):
            box=boxes[row*6+stage];x,y,w,h=[box[k] for k in ['x','y','width','height']]
            crop=(round(x),round(y),round(x+w),round(y+h))
            assert ImageChops.difference(old.crop(crop),new.crop(crop)).getbbox() is None,(entry['file'],item['key'],stage+1)
            checked+=1
result={'species':species,'variants':len(index),'cells':checked,'pixel_identical':True,
        'method':'Compare same 64px article crops in before/after PNGs', 'excluded_species':sorted(changed)}
(current.parent/'unchanged-species.json').write_text(json.dumps(result,indent=2))
print(checked,'untouched species/stage/outfit/surface cells are pixel-identical')
