"""Resolve CDP native sampling stacks only against the matching ELF build ID."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--debug-file',type=Path,required=True);p.add_argument('--build-id',required=True);args=p.parse_args()
notes=subprocess.run(['readelf','-n',str(args.debug_file)],capture_output=True,text=True,check=True).stdout
ids=re.findall(r'Build ID: ([0-9a-f]+)',notes)
if ids!=[args.build_id.lower()]:raise ValueError('Debug ELF build ID mismatch')
raw=args.directory/'native-profile.json.gz'
profile=json.load(gzip.open(raw,'rt'))['profile']
modules=[m for m in profile['modules'] if m['uuid'].lower() in (args.build_id.lower(),args.build_id.lower()+'0')]
if len(modules)!=1:raise ValueError('Profile module build ID mismatch')
module=modules[0];base=int(module['baseAddress'],16);limit=base+module['size']
addresses=sorted({int(frame.split()[0],16) for sample in profile['samples'] for frame in sample['stack'] if base<=int(frame.split()[0],16)<limit})
lines=subprocess.run(['addr2line','-f','-C','-e',str(args.debug_file)],input=''.join(hex(a-base)+'\n' for a in addresses),text=True,capture_output=True,check=True).stdout.splitlines()
if len(lines)!=2*len(addresses):raise ValueError('Symbolizer output count mismatch')
symbols={hex(a):{'offset':hex(a-base),'function':lines[2*i],'location':lines[2*i+1]} for i,a in enumerate(addresses)}
for sample in profile['samples']:
    sample['symbolized_stack']=[symbols.get(frame.split()[0],{'function':frame})['function'] for frame in sample['stack']]
with gzip.open(args.directory/'symbolized-profile.json.gz','wt') as stream:json.dump(profile,stream)
(args.directory/'symbols.json').write_text(json.dumps(symbols,indent=2)+'\n')
metadata={'acceptance':False,'build_id':args.build_id,'profile_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
          'debug_sha256':hashlib.sha256(args.debug_file.read_bytes()).hexdigest(),'samples':len(profile['samples']),
          'resolved_chromium_frames':sum(s['function']!='??' for s in symbols.values()),'total_chromium_frames':len(symbols),
          'scope':'Sampled native allocation stacks in the target renderer. Not complete RSS accounting, not a memory acceptance measurement, and not causal attribution by itself.'}
(args.directory/'symbolization.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps(metadata,indent=2))
