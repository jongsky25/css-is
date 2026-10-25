"""Correlate diagnostic SIGUSR2 wall spans with raw owned callback spans.

This is causal-attribution evidence, not an adjusted acceptance measurement.
Never subtract these durations from the recorded performance gate.
"""
import argparse
import bisect
import gzip
import json
import struct
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
root=args.directory;rows=[]
for trace in sorted(root.glob('*-trace.json.gz')):
    events=json.load(gzip.open(trace))['traceEvents']
    start=next(e['ts'] for e in events if e.get('name')=='avatar-input-start')
    end=next(e['ts'] for e in events if e.get('name')=='avatar-input-end')
    calls=[e for e in events if e.get('name')=='FunctionCall' and e.get('ph')=='X' and '/static/js/avatars.js' in e.get('args',{}).get('data',{}).get('url','') and start<=e['ts']<end]
    cache={};analyses=[]
    for call in calls:
        pid=call['pid']
        if pid not in cache:
            path=root/'signals'/f'{pid}.bin'
            raw=path.read_bytes() if path.exists() else gzip.open(str(path)+'.gz','rb').read()
            count,overflow=struct.unpack_from('<QQ',raw)
            assert overflow==0 and 0<count<=262144
            spans=[(a/1000,b/1000) for a,b in struct.iter_unpack('<QQ',raw[16:16+count*16])]
            assert all(a<=b for a,b in spans)
            assert spans[0][0]<start and spans[-1][1]>end, 'Native and trace clocks/windows do not align'
            cache[pid]=(spans,[b for a,b in spans])
        spans,ends=cache[pid];a=call['ts'];b=a+call['dur'];i=bisect.bisect_right(ends,a);overlap=0
        while i<len(spans) and spans[i][0]<b:
            left,right=spans[i];overlap+=max(0,min(b,right)-max(a,left));i+=1
        if call['dur']>50000:
            analyses.append({'callback_wall_ms':call['dur']/1000,'inside_original_throttle_handler_ms':overlap/1000,'unclassified_remainder_ms':(call['dur']-overlap)/1000,'handler_fraction':overlap/call['dur'],'function':call['args']['data'],'ts_us':a})
    rows.append({'trace':trace.name,'owned_calls':len(calls),'over50_callbacks':analyses,'handler_records':sum(len(v[0]) for v in cache.values()),'max_handler_wall_ms':max((b-a)/1000 for spans,ends in cache.values() for a,b in spans),'long_handlers_in_input_window':[{'start_from_window_ms':(a-start)/1000,'wall_ms':(b-a)/1000} for spans,ends in cache.values() for a,b in spans if a<end and b>start and b-a>50000]})
result={'method':'CLOCK_MONOTONIC spans around unchanged original SIGUSR2 handler, correlated with devtools.timeline FunctionCall intervals on same renderer PID. Diagnostic wrapper overhead remains a limitation; no budget adjustment or subtraction for acceptance.','samples':rows}
(root.parent/'signal-analysis.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
