"""Offline CPU-context summary of frozen control diagnostics; never qualification."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from scripts.avatar_baseline.control_phase_timing import audit


def cpu_delta(before, after):
    if len(before)!=len(after) or len(before)<8:
        raise ValueError('Invalid aggregate CPU fields')
    ticks=[y-x for x,y in zip(before,after)]
    # Linux guest/guest_nice are already included in user/nice.
    if any(n<0 for n in ticks[:8]):raise ValueError('Invalid aggregate CPU delta')
    return sum(ticks[:8]),ticks[7]


def summarize(root, repo):
    checked=audit(root,repo)
    result={'acceptance':False,'instrument_qualified_for_application_calibration':False,
            'audit_status':checked['status'],'audit_errors':checked['errors'],
            'harness_commit':checked['harness_commit'],'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'cohorts':[]}
    for entry in checked['cohorts']:
        index=entry['index'];path=root/f'{index}-control'/'capture.json.gz'
        p=json.load(gzip.open(path,'rt'));d=p['control_timing'];phases=[];totals=defaultdict(float)
        for row in d['phases']:
            a,b=row['before'],row['after']
            total,steal=cpu_delta(a['system_cpu_ticks'],b['system_cpu_ticks'])
            totals['cpu_total_ticks']+=total;totals['steal_ticks']+=steal
            phase={'index':row['index'],'phase':row['phase'],'wall_ms':(row['end_ns']-row['begin_ns'])/1e6,
                   'system_cpu_total_ticks':total,'system_steal_ticks':steal,
                   'system_steal_fraction':steal/total if total else None,
                   'main_thread_runqueue_wait_ms':{k:(b['processes'][k]['main_thread_schedstat'][1]-a['processes'][k]['main_thread_schedstat'][1])/1e6
                       for k in d['pids'] if 'main_thread_schedstat' in a['processes'][k] and 'main_thread_schedstat' in b['processes'][k]}}
            if phase['phase']=='navigation':
                nav=p['stages'][phase['index']]['navigation_timing'];phase['browser_navigation_ms']=nav['duration']
                phase['host_minus_browser_ms']=phase['wall_ms']-nav['duration']
            phases.append(phase)
        result['cohorts'].append({'index':index,'capture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'duration_ms':entry.get('duration_ms'),'phase_ms':entry.get('phase_ms'),'telemetry_ms':entry.get('telemetry_ms'),
            'throttle_ms':entry.get('throttle_ms'),'system_steal_ticks':totals['steal_ticks'],
            'system_cpu_total_ticks':totals['cpu_total_ticks'],
            'system_steal_fraction':totals['steal_ticks']/totals['cpu_total_ticks'] if totals['cpu_total_ticks'] else None,
            'optional_counter_availability':d['initial']['optional'],'phases':phases})
    result['limits']='CPU steal is aggregate virtual CPU context, not per-process waiting or a conversion to wall time. Main-thread waits exclude other threads and blocked I/O. Snapshot reads are not atomic. This new telemetry does not retroactively establish the cause of v12 control variation, qualify the instrument, or authorize discarding slow samples.'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.write_text(json.dumps(summarize(a.root,Path(__file__).resolve().parents[2]),indent=2)+'\n')
