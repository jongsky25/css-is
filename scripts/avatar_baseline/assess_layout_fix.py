"""Assess the frozen geometry fix against every retained 2B gate."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

root=Path('docs/avatars/increment2b');out=root/'layout-fix'
read=lambda path:json.loads(path.read_text())
env=read(out/'native-control/application/environment.json')
for name,digest in env['source_sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
assert subprocess.check_output(['stat','-f','-c','%T','.'],text=True).strip()=='overlayfs'
assert '260 passed' in (out/'validation-tests.txt').read_text()
assert '6 passed' in (out/'functional/tests.txt').read_text()
assert read(out/'artwork-equivalence.json')['svg_equivalence_checks']==1734
pixels=read(out/'visual/unchanged-species.json')
assert pixels['cells']==4896 and pixels['species']==16 and pixels['pixel_identical']
geometry=read(out/'functional/geometry-behavior.json')
assert geometry['steady_input_live_geometry_reads']==0
assert geometry['geometry_listeners_before']==geometry['geometry_listeners_after_20_evaluations']
assert all(r['absolute_error_deg']<=.15 for r in read(out/'functional/transition-geometry.json'))
assert read(out/'functional/static-preview-policy.json')['active_replay_offset_width_reads']==0
assert read(out/'functional/unused-head-geometry.json')['svg_head_bounds_reads']==0
rig=read(out/'visual/motion-rig-check.json')
assert rig['cases']==486 and len(rig['reduced_motion_checks'])==21
assert read(out/'functional/application/environment.json')['source_sha256']==env['source_sha256']
focused={}
for kind in ['fern','mushroom','succulent']:
    data=read(out/f'native-control/{kind}/native-control.json')
    assert data['source_commit']==env['source_commit'] and data['after_only'] and data['kind']==kind
    assert len(data['samples'])==5
    samples=[]
    for r in data['samples']:
        assert r['kind']==kind and r['mature'] and r['cpu']==4 and r['seconds']==30 and r['version']=='after'
        scripts=[s for l in r['native_long_animation_frames'] for s in l['scripts'] if '/static/js/avatars.js' in s['sourceURL'] or '/static/js/avatar-audio.js' in s['sourceURL']]
        maximum=max((s['duration'] for s in scripts),default=0)
        frame=r['scenario']['frame_p95_ms']
        samples.append({'run':r['run'],'frame_p95_ms':frame,'max_reported_owned_script_ms':maximum,'passed':not r['errors'] and frame<=33 and maximum<=50})
    focused[kind]={'samples':samples,'passed':all(s['passed'] for s in samples)}
result={'status':'blocked','source_commit':env['source_commit'],'focused':focused,'primary_samples':0,
        'limits':['Zero reported native owned duration means no owned script in a reported long frame, not zero CPU.',
                  'CPU-throttled local Chromium is not a physical-phone or 60fps claim.',
                  'Original failed cohorts and all outliers retained; budgets and acceptance scenarios unchanged.',
                  'Selected offscreen animation, chase/idle/roam timers and same-document listener retention remain pre-existing release blockers. Static picker thumbnails are resolved.']}
control=read(out/'throttle-control/empty-control.json')
result['empty_callback_control']={'file':'layout-fix/throttle-control/empty-control.json',
    'source':control['source'],'max_empty_callback_ms':max(r['max_empty_callback_ms'] for r in control['samples']),
    'samples':len(control['samples']),
    'limit':'Blank page without avatars/application code reports143ms for an empty callback atCPU1. Native script invoker duration alone cannot establish avatar work as the cause. This does not waive any gate.'}
gates={'focused_native':all(c['passed'] for c in focused.values())}
primary=out/'application/summary.json'
if primary.exists():
    summary=read(primary);comparison=read(out/'comparison.json')
    result['primary_samples']=summary['samples']
    gates['full20_complete']=summary['full_duration_complete'] and comparison['complete']
    gates.update(comparison['gates'])
    rows=[r for name in ['False-cold','False-warm','True-cold','True-warm'] for r in read(out/f'application/{name}.json')]
    assert len(rows)==20 and all(r['seconds']==30 and r['chromium']=='154.0.8037.57' and r['cpu_rate']==(4 if r['mobile'] else 1) for r in rows)
    primary_env=read(out/'application/environment.json')
    assert primary_env['source_sha256']==env['source_sha256'] and primary_env['source_commit']==env['source_commit']
    secondary={}
    for g in comparison['groups']:
        for scenario,metrics in g['scenarios'].items():
            for metric,budget in [('lcp_ms',100),('interaction_duration_per_run_median_ms',20),('renderer_rss_sum_bytes',10*1048576),('js_heap_bytes',10*1048576)]:
                if metric not in metrics:continue
                # Include Home heap and idle RSS as well as secondary surfaces.
                delta=metrics[metric]['median_delta']
                secondary[f"{g['mobile']}-{g['cache']}-{scenario}-{metric}"]={'delta':delta,'budget':budget,'passed':delta<=budget}
    result['secondary']=secondary;gates['all_scenario_latency_memory']=all(s['passed'] for s in secondary.values())
    control=read(root/'reproduced-overlay-control/application/False-cold.json')
    control_env=read(root/'reproduced-overlay-control/application/environment.json')
    for key in ['chromium','playwright','python','platform','fixture_date_local','random_seed']:
        assert primary_env[key]==control_env[key],key
    values=[r['scenarios']['home_idle']['lcp_ms'] for r in rows if not r['mobile'] and r['cache']=='cold']
    previous=[r['scenarios']['home_idle']['lcp_ms'] for r in control]
    matched={'current_values_ms':values,'control_values_ms':previous,'current_median_ms':statistics.median(values),'current_worst_ms':max(values),'control_median_ms':statistics.median(previous),'median_delta_ms':statistics.median(values)-statistics.median(previous),'budget_ms':100}
    result['matched_control']=matched;gates['matched_overlay_lcp']=matched['median_delta_ms']<=100
else:gates['full20_complete']=False
for folder in ['native-functional','care']:
    path=out/f'{folder}/application/environment.json'
    if path.exists():
        other=read(path)
        assert other['source_sha256']==env['source_sha256'] and other['source_commit']==env['source_commit']
native_path=out/'native-functional/application/native-visibility-touch.json'
if native_path.exists():
    native=read(native_path)
    gates['native_hidden_touch_keyboard']=native['hidden_end']['hidden'] and native['hidden_end']['frame_count']==0 and native['touch_drag_changed_style'] and bool(native['keyboard_nudge_style'])
    gates['static_picker']=not native['picker_animations']
else:gates['native_hidden_touch_keyboard']=gates['static_picker']=False
care_path=out/'care/live-plant-care.json'
if care_path.exists():
    care=read(care_path)
    gates['persisted_care']=([r['kind'] for r in care['results']]==['fern','mushroom','succulent'] and all(r['care_persisted'] and r['wet_soil_visible'] for r in care['results']))
else:gates['persisted_care']=False
result['gates']=gates;result['status']='complete' if all(gates.values()) else 'blocked'
result['next_step']='3A: dog, rabbit, bird and turtle; baseline release blockers remain separate' if result['status']=='complete' else 'Resolve failed gates before starting3A.'
(out/'assessment.json').write_text(json.dumps(result,indent=2))
(root/'assessment.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'status':result['status'],'gates':gates},indent=2))
