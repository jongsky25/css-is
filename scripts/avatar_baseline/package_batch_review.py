"""Package portable numeric/visual evidence, retaining hashes for full raw traces."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
files=sorted(f for f in a.directory.rglob('*') if f.is_file() and f.name!='review-manifest.json')
manifest={'source_run_id':os.getenv('GITHUB_RUN_ID'),'source_commit':os.getenv('GITHUB_SHA'),'files':{str(f.relative_to(a.directory)):{'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest(),'bytes':f.stat().st_size} for f in files},'compact_includes':['.json','.xml','.txt','.png'],'full_evidence':'All files including compressed traces are retained in the full workflow artifact.'}
path=a.directory/'review-manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open(a.output,'w:gz',compresslevel=9) as archive:
 for f in [*files,path]:
  if f.suffix in manifest['compact_includes']:archive.add(f,arcname=str(f.relative_to(a.directory)),recursive=False)
print('Review archive bytes:',a.output.stat().st_size)
assert a.output.stat().st_size<25*1024*1024,'Compact transport budget exceeded; full artifact remains retained.'
