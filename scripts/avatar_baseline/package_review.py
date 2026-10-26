"""Retain all JSON/XML/log evidence and hashes of the separately retained traces."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
root=args.directory.resolve()

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

files=[path for path in sorted(root.rglob('*')) if path.is_file()]
manifest={'source_run_id':40247047928,
          'source_run_url':'https://github.com/jongsky25/css-is/actions/runs/40247047928',
          'files':{str(p.relative_to(root)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files},
          'packaged':'All JSON, XML and text logs; binary screenshots and compressed traces remain in source artifact and are hashed here.'}
(root/'review-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open('avatar-2b-review.tar.gz','w:gz',compresslevel=9) as archive:
    for path in [*files,root/'review-manifest.json']:
        if path.suffix in {'.json','.xml','.txt'}:
            archive.add(path,arcname=str(path.relative_to(root)),recursive=False)
assert Path('avatar-2b-review.tar.gz').stat().st_size < 25*1024*1024, 'Review bundle exceeds transport budget; full original artifact is preserved.'
print('Numeric evidence bundle bytes:',Path('avatar-2b-review.tar.gz').stat().st_size)
