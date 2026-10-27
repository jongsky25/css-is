"""Symbolize observed page-request callers and pair captured address lifetimes."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.avatar_baseline.analyze_page_history import audit

BUILD='1c5dca8527a61d07372e489142bee26af1bcaf71'
DEBUG=Path('/workspace/scratch/chromium156-security-symbols/usr/lib/debug/.build-id/1c/5dca8527a61d07372e489142bee26af1bcaf71.debug')


def lifetimes(events, symbols, begin, end):
    active={};pooled=set();rows=[];unknown=[]
    for i,e in sorted(enumerate(events),key=lambda pair:pair[1]['returned_ns']):
        if not int(e['page'],16):continue
        key=(e['backend'],e['page'])
        if e['kind']=='allocate':
            if key in active:raise ValueError('Address lifetime overlap')
            functions=[symbols[f['offset']]['function'] if 'offset' in f else f['external'] for f in e['stack']]
            caller=next((n for n in functions if n.startswith('blink::')),None)
            relation=('inside' if begin<=e['begin_ns']<=e['returned_ns']<=end else
                      'outside' if e['returned_ns']<begin or e['begin_ns']>end else 'boundary_overlap')
            row={'event_index':i,'backend':e['backend'],'page':e['page'],'phase':e['phase'],
                 'begin_ns':e['begin_ns'],'returned_ns':e['returned_ns'],
                 'window_relation':relation,'address_seen_pooled':key in pooled,
                 'functions':functions,'nearest_blink_caller':caller,
                 'pool_event_index':None,'pool_return_ns':None}
            rows.append(row);active[key]=row;pooled.discard(key)
        else:
            row=active.pop(key,None)
            if row:
                row['pool_event_index']=i;row['pool_return_ns']=e['returned_ns']
            else:unknown.append({'event_index':i,**e})
            pooled.add(key)
    callers=defaultdict(lambda:{'requests':0,'returned_within_window':0,'reused_address_requests':0})
    inclusive=defaultdict(int)
    for row in rows:
        if row['window_relation']!='inside':continue
        data=callers[row['nearest_blink_caller'] or '<no resolved Blink caller>']
        data['requests']+=1
        data['returned_within_window']+=row['pool_return_ns'] is not None and row['pool_return_ns']<=end
        data['reused_address_requests']+=row['address_seen_pooled']
        for name in set(row['functions']):inclusive[name]+=1
    return {'lifetimes':rows,'unmatched_pool_returns':unknown,
            'exclusive_nearest_blink_callers':dict(sorted(callers.items(),key=lambda kv:(-kv[1]['requests'],kv[0]))),
            'inclusive_function_request_counts':dict(sorted(inclusive.items(),key=lambda kv:(-kv[1],kv[0])))}


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--debug-file',type=Path,default=DEBUG);a=p.parse_args();repo=Path(__file__).resolve().parents[2]
    plan=json.loads((a.root/'experiment.json').read_text());check=audit(a.root,repo,plan['harness_commit'])
    if check['status'] not in ('calibration_passed','complete_history_diagnostic'):raise ValueError('Unqualified capture')
    notes=subprocess.check_output(['readelf','-n',str(a.debug_file)],text=True,stderr=subprocess.PIPE)
    if 'Build ID: '+BUILD not in notes:raise ValueError('Symbol build mismatch')
    records=[]
    for slot in check['cohorts']:
        if slot['mode']!='probe':continue
        path=a.root/f"{slot['index']:02d}-{slot['arm']}"/'page-history.json.gz'
        raw=json.load(gzip.open(path,'rt'));records.append((slot,raw))
    offsets=sorted({f['offset'] for _,r in records for e in r['native']['history']['events'] for f in e['stack'] if 'offset' in f},key=lambda n:int(n,16))
    lines=subprocess.run(['addr2line','-f','-C','-e',str(a.debug_file)],input='\n'.join(offsets)+'\n',text=True,capture_output=True,check=True).stdout.splitlines()
    if len(lines)!=2*len(offsets):raise ValueError('Incomplete symbol output')
    symbols={o:{'function':lines[2*i],'location':lines[2*i+1]} for i,o in enumerate(offsets)}
    result={'acceptance':False,'build_id':BUILD,'harness_commit':plan['harness_commit'],
            'debug_sha256':hashlib.sha256(a.debug_file.read_bytes()).hexdigest(),
            'offsets':len(offsets),'resolved_offsets':sum(v['function']!='??' for v in symbols.values()),
            'symbols':symbols,'cohorts':[],
            'limits':'Caller is the observed normal-page request trigger, not owner of all objects in that page. Address reuse after a pool return does not prove a pool hit or continuous physical backing: release/unmap is not hooked. Unknown initial pages, unobserved/inlined entries, large pages and in-buffer allocations are outside coverage. Export/window boundaries censor unfinished calls/lifetimes. Inclusive stack counts overlap; never sum them. Injected RSS cannot qualify acceptance.'}
    for slot,r in records:
        data=lifetimes(r['native']['history']['events'],symbols,r['navigation_begin_ns'],r['navigation_end_ns'])
        result['cohorts'].append({'index':slot['index'],'arm':slot['arm'],**data})
    with gzip.open(a.out,'wt') as f:json.dump(result,f)
    print(json.dumps({'cohorts':len(result['cohorts']),'offsets':result['offsets'],'resolved':result['resolved_offsets']}))


if __name__=='__main__':main()
