import gzip,json,subprocess,hashlib,collections
from pathlib import Path
root=Path('/workspace/scratch/collection-cppgc')
debug=Path('/workspace/scratch/chromium156-security-symbols/usr/lib/debug/.build-id/1c/5dca8527a61d07372e489142bee26af1bcaf71.debug')
build='1c5dca8527a61d07372e489142bee26af1bcaf71'
assert 'Build ID: '+build in subprocess.check_output(['readelf','-n',str(debug)],text=True)
profiles=[];offsets=set()
for p in sorted(root.glob('[0-3]-*/*-native.json.gz')):
 d=json.load(gzip.open(p,'rt'))['profile']; mods=[m for m in d['modules'] if m['uuid'].lower() in (build,build+'0')]; assert len(mods)==1
 base=int(mods[0]['baseAddress'],16);limit=base+mods[0]['size']
 for sample in d['samples']:
  for frame in sample['stack']:
   a=int(frame.split()[0],16)
   if base<=a<limit:offsets.add(a-base)
 profiles.append((p,d,base,limit))
offsets=sorted(offsets)
lines=subprocess.check_output(['addr2line','-f','-C','-e',str(debug)],input=''.join(hex(a)+'\n' for a in offsets),text=True).splitlines(); assert len(lines)==len(offsets)*2
symbols={hex(a):lines[2*i] for i,a in enumerate(offsets)}
(root/'native-symbols.json').write_text(json.dumps(symbols,indent=2))
summary=[]
for p,d,base,limit in profiles:
 grouped=collections.Counter()
 for s in d['samples']:
  s['symbols']=[symbols.get(hex(int(f.split()[0],16)-base),f) for f in s['stack']]
  # First non-allocator call identifies a sample bucket; each sample counted once.
  owner=next((f for f in s['symbols'] if any(t in f for t in ['blink::','v8::','Sk','cc::']) and not any(t in f for t in ['Partition','Alloc','malloc'])),s['symbols'][min(5,len(s['symbols'])-1)])
  grouped[owner]+=s['total']
 with gzip.open(p.with_name(p.name.replace('-native','-symbolized')),'wt') as f:json.dump(d,f)
 summary.append({'cohort':p.parent.name,'checkpoint':p.name.removesuffix('-native.json.gz'),'samples':len(d['samples']),'sample_weight_total':sum(s['total'] for s in d['samples']),'largest_buckets':grouped.most_common(15)})
(root/'native-summary.json').write_text(json.dumps({'acceptance':False,'build_id':build,'debug_sha256':hashlib.sha256(debug.read_bytes()).hexdigest(),'resolved_offsets':len(symbols),'note':'Sampling estimates cover target renderer only; bucket totals are not RSS and do not identify retention roots.','records':summary},indent=2))
print('profiles',len(profiles),'offsets',len(symbols))
