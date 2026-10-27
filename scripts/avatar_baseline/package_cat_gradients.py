"""Content-addressed evidence packing; identical files are stored only once."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def pack(roots, target):
    paths = {}; blobs = {}
    for label, root in roots.items():
        for file in sorted(root.rglob('*')):
            if not file.is_file():continue
            data = file.read_bytes(); digest = hashlib.sha256(data).hexdigest()
            paths[label+'/'+file.relative_to(root).as_posix()] = digest
            blobs.setdefault(digest, data)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for digest, data in sorted(blobs.items()):archive.writestr('blobs/'+digest, data)
        archive.writestr('paths.json', json.dumps(paths, indent=2))
    return {'archive_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'logical_files':len(paths), 'unique_blobs':len(blobs), 'paths':paths}


def unpack(archive_path, destination):
    with zipfile.ZipFile(archive_path) as archive:
        paths = json.loads(archive.read('paths.json'))
        for name, digest in paths.items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe evidence path')
            data = archive.read('blobs/'+digest)
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Evidence hash mismatch')
            target = destination/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return paths


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);parser.add_argument('--unpack-to',type=Path,required=True)
    args=parser.parse_args();print('Verified and reconstructed',len(unpack(args.archive,args.unpack_to)),'files')
