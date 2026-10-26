"""Symbolize archived native samples; allocation stacks are not retaining paths."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

BUILD_ID='1c5dca8527a61d07372e489142bee26af1bcaf71'
MOUNTS=(1,5,10,15,20)


def normalize(profile):
    modules=[m for m in profile['modules'] if m['uuid'].lower() in (BUILD_ID,BUILD_ID+'0')]
    if len(modules)!=1:raise ValueError('Native module build ID mismatch')
    module=modules[0];base=int(module['baseAddress'],16);limit=base+module['size']
    samples=[]
    for sample in profile['samples']:
        if type(sample['size']) is not int or sample['size']<=0 or type(sample['total']) is not int or sample['total']<=0:
            raise ValueError('Invalid native sample size')
        frames=[]
        for frame in sample['stack']:
            address=int(frame.split()[0],16)
            frames.append({'offset':hex(address-base)} if base<=address<limit else {'external_frame':frame})
        samples.append({'size':sample['size'],'total':sample['total'],'frames':frames})
    return samples


def load_profiles(root):
    manifest=json.loads((root/'manifest.json').read_text())
    expected=['0-original.zip','1-current.zip','2-current.zip','3-original.zip']
    if [a['name'] for a in manifest['archives']]!=expected:raise ValueError('Incomplete archived cohorts')
    result=[];checked=0
    for archive in manifest['archives']:
        path=root/archive['name']
        if path.stat().st_size!=archive['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=archive['sha256']:
            raise ValueError('Archive identity mismatch')
        with zipfile.ZipFile(path) as z:
            if len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(archive['files']):raise ValueError('Archive inventory mismatch')
            for name,digest in archive['files'].items():
                if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError('Member identity mismatch')
                checked+=1
            checkpoints={r['checkpoint']:r for r in json.loads(z.read('checkpoints.json'))}
            for mount in MOUNTS:
                label=f'navigation_{mount}';name=label+'-native.json.gz'
                raw=z.read(name);samples=normalize(json.loads(gzip.decompress(raw))['profile'])
                snap=checkpoints[label]['snapshot']
                result.append({'cohort':archive['name'][:-4],'checkpoint':label,
                    'profile_sha256':hashlib.sha256(raw).hexdigest(),'samples':samples,
                    'documents':snap['dom_counters']['documents'],'js_heap_bytes':snap['js_heap_bytes'],
                    'renderer_rss_bytes':snap['renderer_rss_sum_bytes']})
    return result,checked


def summarize(profiles,symbols):
    output=[]
    for profile in profiles:
        functions=collections.defaultdict(lambda:{'sample_count':0,'estimated_bytes':0})
        for sample in profile['samples']:
            stack=[symbols[f['offset']]['function'] if 'offset' in f else f['external_frame'] for f in sample['frames']]
            sample['symbolized_stack']=stack
            # Inclusive attribution: count each function once per sample; NEVER sum functions.
            for function in set(stack):
                functions[function]['sample_count']+=1
                functions[function]['estimated_bytes']+=sample['total']
        output.append({**profile,'sample_count':len(profile['samples']),
            'sampled_object_bytes':sum(s['size'] for s in profile['samples']),
            'estimated_native_sample_bytes':sum(s['total'] for s in profile['samples']),
            'inclusive_functions':dict(sorted(functions.items(),key=lambda p:(-p[1]['estimated_bytes'],p[0])))})
    return output


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--debug-file',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    notes=subprocess.check_output(['readelf','-n',str(args.debug_file)],text=True)
    if re.findall(r'Build ID: ([0-9a-f]+)',notes)!=[BUILD_ID]:raise ValueError('Debug build ID mismatch')
    profiles,checked=load_profiles(args.root)
    offsets=sorted({f['offset'] for p in profiles for s in p['samples'] for f in s['frames'] if 'offset' in f},key=lambda n:int(n,16))
    lines=subprocess.run(['addr2line','-f','-C','-e',str(args.debug_file)],input='\n'.join(offsets)+'\n',text=True,capture_output=True,check=True).stdout.splitlines()
    if len(lines)!=len(offsets)*2:raise ValueError('Incomplete symbolizer output')
    symbols={o:{'function':lines[i*2],'location':lines[i*2+1]} for i,o in enumerate(offsets)}
    result={'acceptance':False,'new_measurements':0,'build_id':BUILD_ID,
        'debug_sha256':hashlib.sha256(args.debug_file.read_bytes()).hexdigest(),
        'verified_archive_members':checked,'resolved_offsets':sum(s['function']!='??' for s in symbols.values()),
        'total_offsets':len(symbols),'symbols':symbols,'profiles':summarize(profiles,symbols),
        'limits':'Archived native malloc/partition samples only. size is sampled object size; total is a sampling estimate. Inclusive functions overlap: never sum their weights. Allocation stack is not a retaining path. No JS allocation profiler, heap snapshot, forced GC or RSS subtraction. Historical residency cohorts are separate from the newer timing cohorts.'}
    with gzip.open(args.out,'wt') as stream:json.dump(result,stream)
    print(json.dumps({k:result[k] for k in ['verified_archive_members','resolved_offsets','total_offsets']}))


if __name__=='__main__':main()
