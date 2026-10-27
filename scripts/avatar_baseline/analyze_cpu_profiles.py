"""CPU attribution summaries; profile samples and CPU counters are distinct units."""
import collections
import heapq
import math


def python_summary(profile):
    if (profile['yappi_version'] != '1.7.3' or profile['python_clock'] != 'cpu' or
        profile['python_all_threads'] is not True or profile['acceptance'] is not False):
        raise ValueError('Python profile clock/config mismatch')
    functions = profile['functions']
    if not functions or len({f['index'] for f in functions}) != len(functions):
        raise ValueError('Missing or duplicate Python functions')
    identity = lambda f: (f.get('name'), f.get('module'), f.get('lineno'))
    identities = {identity(f):f['index'] for f in functions}
    if len(identities) != len(functions):raise ValueError('Ambiguous Python function identity')
    edges = []
    for f in functions:
        if any(not math.isfinite(f[k]) or f[k] < 0 for k in ('ttot','tsub','ncall','nactualcall')) or (f['nactualcall'] > 0 and f['tsub'] > f['ttot'] + 1e-6):
            raise ValueError('Invalid Python CPU duration')
        for child in f['children']:
            if identity(child) not in identities:raise ValueError('Unknown Python child identity')
            edges.append({'parent_index':f['index'],'raw_child_index':child['index'],
                          'resolved_child_index':identities[identity(child)]})
    if len(profile['threads']) < 2 or sum(f['tsub'] for f in functions) <= 0:
        raise ValueError('Missing all-thread CPU profile')
    module_self = collections.defaultdict(float)
    for f in functions:
        module_self[f['module']] += f['tsub'] * 1000
    return {'self_cpu_ms':sum(f['tsub'] for f in functions)*1000,
            'open_call_frames':[f['index'] for f in functions if f['nactualcall']==0],
            'resolved_child_edges':edges,'renumbered_child_edges':sum(e['raw_child_index']!=e['resolved_child_index'] for e in edges),
            'thread_cpu_ms':sum(t['ttot'] for t in profile['threads'])*1000,
            'threads':profile['threads'], 'function_count':len(functions),
            'functions_by_self_cpu':sorted(functions,key=lambda f:f['tsub'],reverse=True),
            'module_self_cpu_ms':dict(sorted(module_self.items(),key=lambda x:x[1],reverse=True)),
            'limits':'Yappi CPU clock, all Python threads including driver, server and probes. Self CPU is additive; cumulative/caller times overlap. Profiling overhead is not production cost.'}


def js_summary(profile):
    nodes = {n['id']:n for n in profile['nodes']}
    if len(nodes) != len(profile['nodes']) or not nodes:
        raise ValueError('Duplicate or missing JS nodes')
    samples, deltas = profile.get('samples',[]), profile.get('timeDeltas',[])
    if not samples or len(samples) != len(deltas) or profile['endTime'] <= profile['startTime']:
        raise ValueError('Invalid JS profile bounds/samples')
    for n in nodes.values():
        if any(child not in nodes for child in n.get('children',[])):
            raise ValueError('Unknown JS child')
    weight = collections.Counter();counts = collections.Counter()
    for node, dt in zip(samples,deltas):
        if node not in nodes or not math.isfinite(dt):
            raise ValueError('Unknown JS sample or invalid delta')
        weight[node] += dt;counts[node] += 1
    if sum(deltas) > profile['endTime']-profile['startTime']+2000:
        raise ValueError('JS samples exceed profile window')
    signed = sum(d < 0 for d in deltas)
    ordered = counts.most_common() if signed else weight.most_common()
    return {'negative_delta_count':signed,'elapsed_weights_available':not signed,
            'sample_count':len(samples),'profile_ms':(profile['endTime']-profile['startTime'])/1000,
            'sampled_elapsed_ms':sum(deltas)/1000,
            'leaf_functions':[{'node':node,'callFrame':nodes[node]['callFrame'],'sample_count':counts[node],
                               'sampled_elapsed_ms':None if signed else weight[node]/1000} for node,value in ordered],
            'limits':'Signed deltas are retained; with nonmonotonic samples only counts, not per-function elapsed weights, are reported. V8 samples are not measured per-function CPU. Idle/program/GC remain explicit. Native rendering and Python are outside V8 stacks.'}


def trace_cpu(events, pid, wall_window=None):
    outside_window = 0
    intervals = [];inclusive = collections.Counter();counts = collections.Counter();missing = collections.Counter()
    for e in events:
        if e.get('ph') != 'X' or e.get('pid') != pid or e.get('tid') != pid:
            continue
        if wall_window is not None and not (wall_window[0] <= e.get('ts', -1) and e.get('ts', -1)+e.get('dur', 0) <= wall_window[1]):
            outside_window += 1
            continue
        if 'tts' not in e or 'tdur' not in e:
            missing[e['name']] += 1
            continue
        if e['tdur'] < 0:
            raise ValueError('Negative trace CPU duration')
        if e['tdur']:
            intervals.append((e['tts'],e['tts']+e['tdur'],e['name']))
        inclusive[e['name']] += e['tdur'];counts[e['name']] += 1
    # Union coverage attributed to the smallest recorded enclosing CPU interval.
    # This prevents nested Layout / FunctionCall / RunTask from being summed twice.
    boundaries = collections.defaultdict(list)
    for i,(start,end,name) in enumerate(intervals):
        boundaries[start].append((1,i));boundaries[end].append((-1,i))
    active = set();heap = [];exclusive = collections.Counter();previous = None
    for point,changes in sorted(boundaries.items()):
        while heap and heap[0][2] not in active:heapq.heappop(heap)
        if previous is not None and heap:
            exclusive[intervals[heap[0][2]][2]] += point-previous
        for kind,i in changes:
            if kind == -1:active.discard(i)
            else:
                active.add(i);start,end,_=intervals[i];heapq.heappush(heap,(end-start,-start,i))
        previous = point
    return {'recorded_cpu_coverage_ms':sum(exclusive.values())/1000,
            'wall_window_us':wall_window,'boundary_or_outside_events':outside_window,
            'innermost_recorded_cpu_ms':{k:v/1000 for k,v in exclusive.most_common()},
            'inclusive_cpu_ms_not_additive':{k:v/1000 for k,v in inclusive.most_common()},
            'event_counts':dict(counts),'events_without_thread_cpu':dict(missing),
            'limits':'Renderer main-thread trace tts/tdur only. Coverage union avoids nesting double-counts; smallest recorded enclosing interval is not a complete native stack. Unrecorded CPU and other threads remain unclassified.'}


def trace_js_profiles(segments, pid, navigation_windows):
    groups=[];frames=collections.Counter();covered=collections.Counter();negative=0;outside=0;sample_count=0
    for segment_index, events in enumerate(segments):
        by_id={}
        for event in sorted(events,key=lambda e:e.get('ts',0)):
            if event.get('pid')!=pid or event.get('name') not in ('Profile','ProfileChunk'):
                continue
            data=event['args']['data'];key=event['id']
            group=by_id.setdefault(key,{'nodes':{},'samples':[],'deltas':[],'starts':[],'start_threads':[]})
            if event['name']=='Profile':
                group['starts'].append(data['startTime']);group['start_threads'].append(event['tid']);continue
            cpu=data.get('cpuProfile',{})
            for node in cpu.get('nodes',[]):
                if node['id'] in group['nodes'] and group['nodes'][node['id']]!=node:
                    raise ValueError('Conflicting V8 trace node')
                group['nodes'][node['id']]=node
            samples=cpu.get('samples',[]);deltas=data.get('timeDeltas',[])
            if len(samples)!=len(deltas):raise ValueError('V8 chunk sample/delta mismatch')
            group['samples'].extend(samples);group['deltas'].extend(deltas)
        for key,g in by_id.items():
            if g['start_threads'] and g['start_threads'] != [pid]:continue
            if len(g['starts'])!=1 or not g['samples']:raise ValueError('Missing/ambiguous V8 trace profile start or samples')
            stamp=g['starts'][0];times=[];group_covered=collections.Counter()
            for node,dt in zip(g['samples'],g['deltas']):
                if node not in g['nodes'] or not math.isfinite(dt):raise ValueError('Unknown V8 trace sample or invalid delta')
                negative+=dt<0;stamp+=dt;times.append(stamp);sample_count+=1
                hits=[n['mount'] for n in navigation_windows if n['low_us']<=stamp<=n['high_us']]
                if not hits:outside+=1;continue
                if len(hits)!=1:raise ValueError('Overlapping navigation profile windows')
                covered[hits[0]]+=1;group_covered[hits[0]]+=1
                frame=g['nodes'][node]['callFrame'];identity=(frame.get('functionName',''),frame.get('url',''),frame.get('lineNumber',-1),frame.get('columnNumber',-1))
                frames[identity]+=1
            groups.append({'segment':segment_index,'id':key,'sample_count':len(g['samples']),
                           'first_sample_us':min(times),'last_sample_us':max(times),'covered_mounts':dict(group_covered)})
    if not groups:raise ValueError('No app-renderer V8 trace profiles')
    missing=[n['mount'] for n in navigation_windows if not covered[n['mount']]]
    return {'groups':groups,'sample_count':sample_count,'negative_deltas_retained':negative,
            'outside_navigation_intervals':outside,'samples_by_mount':dict(covered),'missing_mounts':missing,
            'leaf_functions':[{'function':f[0],'url':f[1],'line':f[2],'column':f[3],'samples':count} for f,count in frames.most_common()],
            'limits':'Trace-based V8 sample counts across contexts, not per-function CPU time. Signed deltas reconstruct sample timestamps; no negative elapsed weights assigned. Idle/program/GC retained; only samples in bounded navigation intervals attributed. Default trace sampler frequency is not claimed to equal a fixed requested interval.'}
