"""Read-only CPU isolation inventory; never reserves CPUs or proves host exclusivity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time

CGROUP_FILES = ['cgroup.controllers','cgroup.type','cpu.max','cpu.weight',
                'cpuset.cpus','cpuset.cpus.effective','cpuset.cpus.exclusive',
                'cpuset.cpus.exclusive.effective','cpuset.cpus.partition']
CPU_FIELDS = ['Architecture','CPU(s)','On-line CPU(s) list','Vendor ID','Model name',
              'Thread(s) per core','Core(s) per socket','Socket(s)',
              'Hypervisor vendor','Virtualization type']


def inventory():
    result={'protocol':'runner-isolation-inventory-v1','acceptance':False,
            'isolation_established':False,'configuration_changed':False,
            'begin_ns':time.monotonic_ns(),'uid':os.getuid(),'affinity_cpus':sorted(os.sched_getaffinity(0)),
            'machine':platform.machine(),'kernel_release':platform.release(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'cgroup_membership':Path('/proc/self/cgroup').read_text().strip(),'cgroup_files':{}}
    for name in CGROUP_FILES:
        path=Path('/sys/fs/cgroup')/name
        try:result['cgroup_files'][name]={'raw':path.read_text().strip(),'writable_by_current_user':os.access(path,os.W_OK)}
        except OSError as error:result['cgroup_files'][name]={'unavailable':type(error).__name__}
    command=subprocess.run(['lscpu'],capture_output=True,text=True,env={**os.environ,'LC_ALL':'C'})
    result['lscpu_exit_code']=command.returncode
    result['cpu_topology']={key.strip():value.strip() for line in command.stdout.splitlines() if ':' in line
                            for key,value in [line.split(':',1)] if key.strip() in CPU_FIELDS}
    detect=subprocess.run(['systemd-detect-virt'],capture_output=True,text=True)
    result['virtualization_detection']={'exit_code':detect.returncode,'value':detect.stdout.strip()}
    # Mount metadata only for this known cgroup mount; omit unrelated mount paths.
    result['cgroup_mounts']=[]
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields=line.split()
        if fields[4]=='/sys/fs/cgroup':
            split=fields.index('-')
            result['cgroup_mounts'].append({'options':fields[5],'filesystem':fields[split+1],'super_options':fields[split+3]})
    result['end_ns']=time.monotonic_ns()
    result['limits']='Guest cpusets and affinity do not prove host CPU reservation. Writability is observed permission, not a successful write test. No provider reservation, capacity change, privilege change, benchmark, quiet-window retry, or CPU-affinity intervention was performed.'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('Refusing to overwrite inventory evidence')
    a.out.write_text(json.dumps(inventory(),indent=2)+'\n')
