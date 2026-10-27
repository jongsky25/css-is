"""Read-only Linux scheduling observations; no process or quota changes."""
import os
from pathlib import Path
import time


def parse_stat(value):
    # comm may contain spaces and ')' characters; fields begin after the LAST ')'.
    fields = value.rsplit(')', 1)[1].split()
    return {'state': fields[0], 'minor_faults': int(fields[7]), 'major_faults': int(fields[9]),
            'user_ticks': int(fields[11]), 'system_ticks': int(fields[12]),
            'start_ticks': int(fields[19])}


def read_task(pid):
    proc = Path(f'/proc/{pid}')
    value = {'pid': pid, 'begin_ns': time.monotonic_ns()}
    try:
        value['stat'] = parse_stat((proc / 'stat').read_text())
        runtime, wait, slices = map(int, (proc / 'schedstat').read_text().split())
        value['schedstat'] = {'runtime_ns': runtime, 'wait_ns': wait, 'timeslices': slices}
    except (OSError, ValueError) as error:
        value['error'] = str(error)
    value['end_ns'] = time.monotonic_ns()
    return value


def read_scheduler(pids, main_pid, sampler_tid):
    begin = time.monotonic_ns()
    cpu_begin = time.thread_time_ns()
    result = {'begin_ns': begin, 'tasks': [], 'errors': []}
    try:
        result['cgroup_cpu'] = {k: int(v) for k, v in
                                (line.split() for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())}
    except (OSError, ValueError) as error:
        result['errors'].append(str(error))
    for pid in sorted(set([*pids, main_pid, sampler_tid])):
        result['tasks'].append(read_task(pid))
    result['reader_cpu_ns'] = time.thread_time_ns() - cpu_begin
    result['end_ns'] = time.monotonic_ns()
    return result


def scheduler_environment():
    result = {'main_pid': os.getpid(), 'clock_ticks_per_second': os.sysconf('SC_CLK_TCK'),
              'affinity': sorted(os.sched_getaffinity(0)), 'files': {}}
    for name in ['/proc/self/cgroup', '/sys/fs/cgroup/cpu.max', '/sys/fs/cgroup/cpuset.cpus.effective',
                 '/sys/fs/cgroup/cpu.pressure', '/proc/sys/kernel/sched_schedstats']:
        try:
            result['files'][name] = {'value': Path(name).read_text().strip()}
        except OSError as error:
            result['files'][name] = {'unavailable': str(error)}
    return result
