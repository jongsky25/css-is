"""Retain every numeric/visual file in independently downloadable archive parts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
files=sorted(f for f in a.directory.rglob('*') if f.is_file() and f.name!='review-manifest.json')
def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
source=json.loads((a.directory/'matrix/assessment.json').read_text())['source_commit']
manifest={'source_run_id':os.getenv('AVATAR_SOURCE_RUN'),'source_commit':source,'audit_commit':os.getenv('GITHUB_SHA'),'files':{str(f.relative_to(a.directory)):{'sha256':digest(f),'bytes':f.stat().st_size} for f in files},'compact_includes':['.json','.xml','.txt','.png'],'full_evidence':'All files including compressed traces remain in the original full workflow artifact. Extract ALL numbered parts into one directory before audit.'}
path=a.directory/'review-manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
selected=[path]+[f for f in files if f.suffix in manifest['compact_includes']]
groups=[];group=[];size=0
for file in selected:
 check_size=file.stat().st_size
 if group and size+check_size>20*1024*1024:groups.append(group);group=[];size=0
 group.append(file);size+=check_size
if group:groups.append(group)
assert len(groups)<=8,'More archive parts than configured upload slots; full raw evidence remains retained.'
parts=[]
for number,group in enumerate(groups,1):
 output=a.output.parent/(a.output.name+f'-{number}.tar.gz')
 with tarfile.open(output,'w:gz',compresslevel=9) as archive:
  for file in group:archive.add(file,arcname=str(file.relative_to(a.directory)),recursive=False)
 assert output.stat().st_size<25*1024*1024,'A part exceeds transport budget; full raw evidence remains retained.'
 parts.append({'file':output.name,'bytes':output.stat().st_size,'sha256':digest(output)})
(a.output.parent/(a.output.name+'-parts.json')).write_text(json.dumps(parts,indent=2)+'\n')
print(json.dumps(parts,indent=2))
