from pathlib import Path
import sys,subprocess,tempfile,json,hashlib
sys.path.insert(0,'scripts/avatar_baseline')
from gallery import CATALOG
from jinja2 import Environment,FileSystemLoader,StrictUndefined
before='f46d7af';changed={'dog','rabbit','bird','turtle'};n=0
with tempfile.TemporaryDirectory() as tmp:
 for file in subprocess.check_output(['git','ls-tree','-r','--name-only',before,'templates'],text=True).splitlines():
  if Path(file).name.startswith('_avatar') or '/_avatar_species/' in file:
   target=Path(tmp)/Path(file).relative_to('templates');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(subprocess.check_output(['git','show',before+':'+file]))
 def module(root):
  e=Environment(loader=FileSystemLoader(root),autoescape=True,undefined=StrictUndefined)
  e.globals.update(avatar_uid=lambda:'equivalent',avatar_month=lambda:0,avatar_outfit=lambda:'default',avatar_family=lambda k:'plant' if k in ['plant','cactus','bonsai','sunflower','fern','mushroom','succulent'] else 'animal',avatar_is_swimmer=lambda k:k in ['fish','dolphin'])
  return e.get_template('_avatars.html').module
 old=module(tmp);new=module('templates')
 for c in CATALOG:
  if c['key'] in changed:continue
  for stage in range(1,7):
   for month,outfit in [(m,'default') for m in range(13)]+[(10,c) for c in ['halloween','halloween_vampire','halloween_pumpkin']]+[(12,'christmas')]:
    for static in [False,True]:
     assert str(old.avatar_svg(c['key'],stage,month,outfit,static_preview=static))==str(new.avatar_svg(c['key'],stage,month,outfit,static_preview=static)),(c,stage,month,outfit,static)
     n+=1
for file in ['static/js/avatars.js','static/js/avatar-audio.js']:
 assert Path(file).read_bytes()==subprocess.check_output(['git','show',before+':'+file])
r={'before':before,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'unchanged_species':12,'exact_svg_comparisons':n,'static_and_interactive':True,'runtime_and_audio_unchanged':True,'changed_species':sorted(changed),'product_sha256':{f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in ['templates/_avatars.html']+['templates/_avatar_species/'+k+'.html' for k in sorted(changed)]}}
Path('docs/avatars/increment3a/unchanged-species.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
