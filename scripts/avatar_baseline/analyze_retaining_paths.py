"""Audit isolated post-forced-GC graphs; never natural/acceptance accounting."""
import argparse
from array import array
from collections import Counter, deque
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from scripts.avatar_baseline.analyze_paired_variance import REFS, required_sources, slot_points, source
from scripts.avatar_baseline.analyze_navigation_timing import timing

HARNESS=['tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py',
         'tests/test_avatar_navigation_timing_browser.py','tests/test_avatar_retaining_paths_browser.py']
ORDER=['original','current','current','original']
EXCLUDED={'weak','shortcut'}


def document_name(name):
    return bool(re.fullmatch(r'(?:Detached )?(?:blink::)?(?:HTML|XML|SVG)?Document(?: /.*)?',name))


def graph(snapshot):
    meta=snapshot['snapshot']['meta'];nodes=snapshot['nodes'];edges=snapshot['edges'];strings=snapshot['strings']
    nf=meta['node_fields'];ef=meta['edge_fields'];ns=len(nf);es=len(ef)
    if not ns or not es or len(nodes)%ns or len(edges)%es:raise ValueError('Malformed graph arrays')
    ni={name:nf.index(name) for name in ['type','name','id','self_size','edge_count']}
    ei={name:ef.index(name) for name in ['type','name_or_index','to_node']}
    nt=meta['node_types'][ni['type']];et=meta['edge_types'][ei['type']]
    count=len(nodes)//ns
    if count!=snapshot['snapshot']['node_count'] or len(edges)//es!=snapshot['snapshot']['edge_count']:
        raise ValueError('Graph count mismatch')
    starts=array('q',[0]);names=[];types=[];ids=set()
    for i in range(count):
        off=i*ns;ident=nodes[off+ni['id']]
        if ident in ids:raise ValueError('Duplicate node ID')
        ids.add(ident)
        name_index=nodes[off+ni['name']];type_index=nodes[off+ni['type']];n=nodes[off+ni['edge_count']]
        if not (type(name_index) is int and 0<=name_index<len(strings) and type(type_index) is int and 0<=type_index<len(nt) and type(n) is int and n>=0):
            raise ValueError('Invalid node metadata')
        names.append(strings[name_index]);types.append(nt[type_index]);starts.append(starts[-1]+n*es)
    if starts[-1]!=len(edges) or not count or types[0]!='synthetic':raise ValueError('Invalid root or adjacency length')
    for off in range(0,len(edges),es):
        target=edges[off+ei['to_node']];kind=edges[off+ei['type']]
        if type(target) is not int or target%ns or not 0<=target//ns<count or type(kind) is not int or not 0<=kind<len(et):
            raise ValueError('Invalid graph edge')
        name=edges[off+ei['name_or_index']]
        if et[kind] not in ['element','hidden'] and (type(name) is not int or not 0<=name<len(strings)):
            raise ValueError('Invalid edge name')
    def node(i):
        off=i*ns
        return {'index':i,'id':nodes[off+ni['id']],'type':types[i],'name':names[i],
                'self_size':nodes[off+ni['self_size']],
                'detachedness':nodes[off+nf.index('detachedness')] if 'detachedness' in nf else None}
    def edge(off):
        kind=et[edges[off+ei['type']]];name=edges[off+ei['name_or_index']]
        return {'type':kind,'name':name if kind in ['element','hidden'] else strings[name]}
    parent=array('q',[-1])*count;via=array('q',[-1])*count;parent[0]=0;queue=deque([0])
    while queue:
        i=queue.popleft()
        for off in range(starts[i],starts[i+1],es):
            if et[edges[off+ei['type']]] in EXCLUDED:continue
            target=edges[off+ei['to_node']]//ns
            if parent[target]<0:parent[target]=i;via[target]=off;queue.append(target)
    def path(i):
        if parent[i]<0:return None
        result=[]
        while i:
            result.append({'from':node(parent[i]),'edge':edge(via[i]),'to':node(i)})
            i=parent[i]
        return list(reversed(result))
    candidates={i:[] for i in range(count) if types[i] in ['native','object'] and document_name(names[i])}
    for i in range(count):
        for off in range(starts[i],starts[i+1],es):
            target=edges[off+ei['to_node']]//ns
            if target in candidates:
                description=edge(off)
                candidates[target].append({'referrer':node(i),'edge':description,
                    'excluded_from_path_search':description['type'] in EXCLUDED,
                    'referrer_path':path(i) if description['type'] not in EXCLUDED else None})
    docs=[{'node':node(i),'representative_path':path(i),'incoming':incoming} for i,incoming in candidates.items()]
    return {'node_count':count,'edge_count':len(edges)//es,'reachable_excluding_weak_shortcut':sum(p>=0 for p in parent),
        'document_like_node_count':len(docs),'document_like_nodes':docs,
        'document_node_types':dict(Counter(d['node']['type'] for d in docs)),
        'document_detachedness':dict(Counter(str(d['node']['detachedness']) for d in docs)),
        'native_context_count':sum(n.startswith('system / NativeContext') for n in names),
        'limits':'Document-like native nodes and JS wrappers may represent the same document; do not add them or equate them to DOM counters. Paths exclude weak and synthetic shortcut edges. Internal/hidden edges and ephemeron semantics require interpretation. One BFS path plus every immediate incoming reference is retained, not all paths or proof of a causal owner.'}


def sealed_row(raw, expected_digest, recovery=None):
    if hashlib.sha256(raw).hexdigest()==expected_digest:return raw,None
    if recovery is None:raise ValueError('Natural evidence changed after snapshot')
    if hashlib.sha256(recovery).hexdigest()!=expected_digest:raise ValueError('Recovery does not match pre-snapshot seal')
    final=json.loads(raw);sealed=json.loads(recovery)
    if len(final)!=1 or len(sealed)!=1:raise ValueError('Invalid sealed row shape')
    final_responses=final[0].pop('responses');sealed_responses=sealed[0].pop('responses')
    if final!=sealed or final_responses[:len(sealed_responses)]!=sealed_responses or len(final_responses)<=len(sealed_responses):
        raise ValueError('Recovery changes more than appended response bookkeeping')
    return recovery,{'sealed_sha256':expected_digest,'postclose_sha256':hashlib.sha256(raw).hexdigest(),
        'appended_responses':final_responses[len(sealed_responses):],
        'all_other_fields_identical':True}


def fixture(repo,ref,name,adapter="ordinal-and-preclose-save-v1"):
    data=source(repo,ref,name)
    if name=='tests/test_avatar_baseline_browser.py':
        replacements=[(b'for run in range(runs):',b"for run in range(int(os.getenv('CSS_AVATAR_RUN_START', '0')), int(os.getenv('CSS_AVATAR_RUN_START', '0')) + runs):"),
            (b'rows.append(row);context.close()',b"rows.append(row); (out/f'{mobile}-{cache}.json').write_text(json.dumps(rows,indent=2)); context.close()" if adapter=="ordinal-and-preclose-save-v1" else b"rows.append(json.loads(json.dumps(row))); (out/f'{mobile}-{cache}.json').write_text(json.dumps(rows,indent=2)); context.close()")]
        for before,after in replacements:
            if data.count(before)!=1:raise ValueError('Fixture adapter mismatch')
            data=data.replace(before,after,1)
    return data


def audit(root,repo,ref,recovery_root=None):
    result={'acceptance':False,'intentional_forced_gc':True,'status':'inconclusive','errors':[],
            'source_hashes_verified':0,'files_verified':0,'sealed_recoveries':[],'cohorts':[]}
    try:
        plan=json.loads((root/'experiment.json').read_text())
        if (plan['protocol']!='retaining-paths-forensic-v1' or plan['harness_commit']!=ref or
            plan['refs']!=REFS or plan['blocks']!=[ORDER] or plan['samples_per_slot']!=1 or plan['seconds']!=30 or
            plan['acceptance'] is not False or plan['browser']!='156.0.8078.47' or plan['budget_bytes']!=10485760 or
            plan['fixture_adapter'] not in ['ordinal-and-preclose-save-v1','ordinal-preclose-frozen-row-v2'] or len(plan['cohorts'])!=4):raise ValueError('Protocol mismatch')
        for name in HARNESS:
            if (root/'harness'/name).read_bytes()!=fixture(repo,ref,name,plan['fixture_adapter']):raise ValueError('Frozen harness mismatch')
        for index,(arm,entry) in enumerate(zip(ORDER,plan['cohorts'])):
            if any(entry.get(k)!=v for k,v in dict(index=index,block=0,position=index,arm=arm,exit_code=0).items()):
                raise ValueError('Failed or invalid slot '+str(index))
            folder=root/f'{index:02d}-{arm}'
            required={'environment.json','False-warm.json','navigation-timing.json','navigation-trace.json.gz','timing-provenance.json','forensic-provenance.json','post-workload.heapsnapshot.json.gz','runner.txt','junit.xml','profile-False-warm.png'}
            if set(entry['files_sha256'])!=required:raise ValueError('Evidence inventory mismatch')
            for name,digest in entry['files_sha256'].items():
                if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:raise ValueError('Evidence hash mismatch')
                result['files_verified']+=1
            env=json.loads((folder/'environment.json').read_text())
            if env['source_commit']!=REFS[arm] or env['chromium']!='156.0.8078.47' or set(env['source_sha256'])!=required_sources(repo,REFS[arm]):raise ValueError('Source identity mismatch')
            for name,digest in env['source_sha256'].items():
                data=fixture(repo,ref,name,plan['fixture_adapter']) if name in HARNESS else source(repo,REFS[arm],name)
                if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Source hash mismatch '+name)
                result['source_hashes_verified']+=1
            natural=json.loads((folder/'timing-provenance.json').read_text());forensic=json.loads((folder/'forensic-provenance.json').read_text())
            if (natural['acceptance'] is not False or natural['allocator_dumps'] is not False or natural['native_sampling'] is not False or natural['snapshots']!=13 or natural['navigation_observations']!=20 or natural['trace_completion'].get('dataLossOccurred') or forensic['acceptance'] is not False or forensic['intentional_forced_gc'] is not True or forensic['natural_trace_closed_before_snapshot'] is not True):raise ValueError('Invalid probe provenance')
            for provenance,name in [(natural,HARNESS[2]),(forensic,HARNESS[3])]:
                if provenance['probe_sha256']!=hashlib.sha256(source(repo,ref,name)).hexdigest():raise ValueError('Probe identity mismatch')
                result['source_hashes_verified']+=1
            expected={'False-warm.json','navigation-timing.json','navigation-trace.json.gz','timing-provenance.json'}
            if set(forensic['natural_evidence_sha256'])!=expected:raise ValueError('Incomplete sealed natural evidence')
            raw_data=(folder/'False-warm.json').read_bytes()
            recovered=None
            for name,digest in forensic['natural_evidence_sha256'].items():
                if name=='False-warm.json':
                    recovery_path=recovery_root/f'{index:02d}-{arm}'/name if recovery_root else None
                    recovery=recovery_path.read_bytes() if recovery_path and recovery_path.exists() else None
                    raw_data,recovered=sealed_row(raw_data,digest,recovery)
                elif digest!=entry['files_sha256'][name]:raise ValueError('Natural evidence changed after snapshot')
            if recovered:result['sealed_recoveries'].append({'index':index,'arm':arm,**recovered})
            if forensic['snapshot_sha256']!=entry['files_sha256']['post-workload.heapsnapshot.json.gz'] or entry['raw_sha256']!=entry['files_sha256']['False-warm.json']:raise ValueError('Raw identity mismatch')
            rows=json.loads(raw_data);points=slot_points(rows,0)
            natural_result=timing(json.load(gzip.open(folder/'navigation-trace.json.gz','rt'))['traceEvents'],json.loads((folder/'navigation-timing.json').read_text()))
            for snap in [*rows[0]['scenarios'].values(),*rows[0]['navigation_trend']]:
                if natural_result['app_pid'] not in [d['pid'] for d in snap['renderer_memory_detail']]:raise ValueError('App renderer mapping mismatch')
            heap=graph(json.load(gzip.open(folder/'post-workload.heapsnapshot.json.gz','rt')))
            result['cohorts'].append({'index':index,'arm':arm,'forensic':forensic,'natural':natural_result,'baseline_points':points,'heap':heap})
        result['status']='complete_forensic_capture_with_sealed_recovery' if result['sealed_recoveries'] else 'complete_forensic_capture'
    except (ValueError,KeyError,TypeError,OSError,subprocess.CalledProcessError) as error:result['errors'].append(repr(error))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--harness-ref',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--sealed-recovery-dir',type=Path)
    args=p.parse_args();repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse',args.harness_ref],cwd=repo,text=True).strip()
    result=audit(args.root,repo,ref,args.sealed_recovery_dir)
    with gzip.open(args.out,'wt') as stream:json.dump(result,stream)
    print(json.dumps({k:result[k] for k in ['status','errors','source_hashes_verified','files_verified']}))
    sys.exit(bool(result['errors']))
