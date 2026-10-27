"""Bounded scheduler/cgroup counter deltas, without causal overclaims."""


def delta(a, b):
    shared = set(a) & set(b)
    result = {k: b[k] - a[k] for k in sorted(shared)}
    if any(v < 0 for v in result.values()):
        raise ValueError('Scheduler counter reset')
    return result


def scheduler_observation(p):
    edges = p['scheduler_edges']
    if len(edges) != 2 or edges[0]['end_ns'] > p['navigation_begin_ns'] or edges[1]['begin_ns'] < p['navigation_end_ns']:
        raise ValueError('Scheduler edges do not bracket navigation')
    main_pid = p['scheduler_environment']['main_pid']
    for edge in edges:
        main = [t for t in edge['tasks'] if t['pid'] == main_pid and 'error' not in t]
        if len(main) != 1:
            raise ValueError('Missing main-thread scheduler edge')
    samples = [edges[0], *(s['scheduler'] for s in p['samples']), edges[1]]
    for i, s in enumerate(samples):
        if s['errors'] or not {'usage_usec', 'nr_periods', 'nr_throttled', 'throttled_usec'} <= s['cgroup_cpu'].keys():
            raise ValueError('Missing cgroup counters')
        if s['end_ns'] < s['begin_ns'] or (i and s['begin_ns'] < samples[i-1]['end_ns']):
            raise ValueError('Overlapping scheduler samples')
        if s['reader_cpu_ns'] < 0 or s['reader_cpu_ns'] > s['end_ns']-s['begin_ns']:
            raise ValueError('Invalid reader CPU duration')
    nav = p['navigation_intervals']
    if [n['mount'] for n in nav] != list(range(1, 21)):
        raise ValueError('Missing navigation intervals')
    for i, n in enumerate(nav):
        if not p['navigation_begin_ns'] <= n['begin_ns'] <= n['goto_end_ns'] <= n['wait_end_ns'] <= p['navigation_end_ns']:
            raise ValueError('Invalid navigation interval')
        if i and n['begin_ns'] < nav[i-1]['wait_end_ns']:
            raise ValueError('Overlapping navigation intervals')
    steps = []
    for a, b in zip(samples, samples[1:]):
        low, high = a['begin_ns'], b['end_ns']
        tasks = []
        by_pid = {t['pid']: t for t in a['tasks']}
        for t in b['tasks']:
            prev = by_pid.get(t['pid'])
            if prev is None or 'error' in prev or 'error' in t:
                continue
            if t['stat']['start_ticks'] != prev['stat']['start_ticks']:
                raise ValueError('PID reused across scheduler samples')
            tasks.append({'pid': t['pid'], 'schedstat_delta': delta(prev['schedstat'], t['schedstat']),
                          'stat_delta': delta({k:v for k,v in prev['stat'].items() if k != 'state'},
                                              {k:v for k,v in t['stat'].items() if k != 'state'})})
        steps.append({'interval_ns': [low, high], 'cgroup_delta': delta(a['cgroup_cpu'], b['cgroup_cpu']),
                      'tasks': tasks, 'overlapping_mounts': [n['mount'] for n in nav if n['begin_ns'] <= high and n['wait_end_ns'] >= low]})
    total = p['navigation_end_ns'] - p['navigation_begin_ns']
    per_nav = []
    for n in nav:
        # Bracket the navigation; boundary counter intervals can overlap adjacent navigations.
        a = max((s for s in samples if s['end_ns'] <= n['begin_ns']), key=lambda s:s['end_ns'], default=edges[0])
        b = min((s for s in samples if s['begin_ns'] >= n['wait_end_ns']), key=lambda s:s['begin_ns'], default=edges[1])
        per_nav.append({**n, 'goto_ms': (n['goto_end_ns']-n['begin_ns'])/1e6,
                        'wait_ms': (n['wait_end_ns']-n['goto_end_ns'])/1e6,
                        'bracket_ns': [a['begin_ns'],b['end_ns']], 'cgroup_delta': delta(a['cgroup_cpu'],b['cgroup_cpu'])})
    first, last = samples[0], samples[-1]
    pid_summary = []
    for t in first['tasks']:
        matched = [v for v in last['tasks'] if v['pid'] == t['pid']]
        if len(matched) != 1 or 'error' in t or 'error' in matched[0]:
            continue
        end = matched[0]
        if t['stat']['start_ticks'] != end['stat']['start_ticks']:
            raise ValueError('PID reused at scheduler edges')
        pid_summary.append({'pid':t['pid'],'schedstat_delta':delta(t['schedstat'],end['schedstat'])})
    return {'cgroup_delta': delta(first['cgroup_cpu'],last['cgroup_cpu']), 'tasks':pid_summary,
            'sample_steps':steps,'navigation':per_nav,
            'reader_cpu_fraction':sum(s['reader_cpu_ns'] for s in samples)/total,
            'max_read_wall_ms':max((s['end_ns']-s['begin_ns'])/1e6 for s in samples),
            'task_read_errors': [t for s in samples for t in s['tasks'] if 'error' in t],
            'limits':'Cgroup counters cover every task in the cgroup, not only avatars. Main-thread schedstat is not all renderer threads. Counter brackets overlap and are not additive by navigation. Missing task reads are retained. No causal attribution from coincidence alone.'}
