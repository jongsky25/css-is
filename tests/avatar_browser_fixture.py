"""Opt-in Linux benchmark affinity; never loaded by application code."""
import os
from pathlib import Path


def historical_art_loader(current_loader, folder):
    """Load original art with callers that support its historical macro API."""
    import subprocess
    from jinja2 import ChoiceLoader, FileSystemLoader
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name in ['_avatars.html', '_avatars_art.html', '_growth.html', 'me.html']:
        (folder / name).write_bytes(subprocess.check_output([
            'git', 'show', '5b580d9:templates/' + name]))
    return ChoiceLoader([FileSystemLoader(folder), current_loader])


def pin_renderer_threads(browser):
    """Keep synthetic-throttle signals and the renderer on the same CPU.

    Chromium's POSIX throttler busy-waits in SIGUSR2 and masks SIGPROF. Pinning
    those two threads together avoids concurrent sender/handler contention.
    Other browser threads retain the process-tree affinity. Record actual pins;
    this changes no browser CPU emulation rate, scenario, sample or budget.
    """
    if os.getenv('CSS_AVATAR_PIN_RENDERER') != '1':
        return []
    assert 1 in os.sched_getaffinity(0)
    system = browser.new_browser_cdp_session()
    pins = []
    try:
        processes = system.send('SystemInfo.getProcessInfo')['processInfo']
        for process in processes:
            if process['type'] != 'renderer':
                continue
            pid = int(process['id'])
            os.sched_setaffinity(pid, {1})
            pins.append({'tid': pid, 'name': 'renderer-main', 'cpus': sorted(os.sched_getaffinity(pid))})
            for task in Path(f'/proc/{pid}/task').iterdir():
                try:
                    name = (task / 'comm').read_text().strip()
                    if name.startswith('CPUThrottling'):
                        tid = int(task.name)
                        os.sched_setaffinity(tid, {1})
                        pins.append({'tid': tid, 'name': name, 'cpus': sorted(os.sched_getaffinity(tid))})
                except FileNotFoundError:
                    pass  # A background thread can exit while enumerating.
    finally:
        system.detach()
    assert any(row['name'] == 'renderer-main' for row in pins)
    return pins


def accepted_frame(value):
    """User-approved 33.3ms ceiling; the callback ceiling remains 50ms."""
    import math
    return isinstance(value, (int, float)) and math.isfinite(value) and value <= 33.3 + 1e-8
