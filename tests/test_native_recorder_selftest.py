from copy import deepcopy
import pytest
from scripts.avatar_baseline.native_recorder_selftest import validate


def event(worker,sequence,when):
    address=(worker<<32)|sequence
    return {'kind':'__selftest','address':hex(address),'backend':hex(address^0x5a5a),
            'thread':100+worker,'phase_id':worker*100000+sequence,'phase_document':worker*100000+sequence,
            'phase_type':1,'begin_ns':when,'callback_ready_ns':when+1,'returned_ns':when+2}


def specimen():
    p={'clock_samples':[{'begin_ns':100+i*10,'native_ns':101+i*10,'end_ns':102+i*10} for i in range(20)]}
    for label,iterations,limit,count,dropped in [('concurrency',256,50000,1024,0),('overflow',17,32,32,36)]:
        events=[event(w,s,1000+(w*iterations+s)*3) for w in range(1,5) for s in range(1,iterations+1)][:count]
        p[label]={'begin_ns':1000,'end_ns':100000,'history':{'record_size':72,'record_capacity':50000,
            'record_limit':limit,'pending_at_snapshot':0,'dropped':dropped,'events':events,
            'snapshot_end_ns':90000,'recorder_backend':'cmodule-buffer-v1','clock_domain':'CLOCK_MONOTONIC',
            'abi':'linux-x64-gum-invocation-v1','toolchain':'internal',
            'storage':{'state_bytes':7200080,'allocated_bytes':7200256,'first_protection':'rw-','last_protection':'rw-'}}}
    return p


def test_complete_clock_concurrency_and_overflow_proof():
    result=validate(specimen())
    assert result['status']=='selftest_passed' and result['immutable_records']==1024
    assert result['overflow_stored']==32 and result['overflow_dropped']==36
    assert result['acceptance'] is False


@pytest.mark.parametrize('bad',['clock','records','threads','duplicate','pointer','phase','pending','overflow','limit','snapshot','abi'])
def test_native_proof_failures_cannot_be_ignored(bad):
    p=specimen();history=p['concurrency']['history']
    if bad=='clock':p['clock_samples'][0]['native_ns']=0
    if bad=='records':history['events'].pop()
    if bad=='threads':
        for e in history['events']:e['thread']=1
    if bad=='duplicate':history['events'][1]['address']=history['events'][0]['address']
    if bad=='pointer':history['events'][0]['backend']='0x0'
    if bad=='phase':history['events'][0]['phase_document']+=1
    if bad=='pending':history['pending_at_snapshot']=1
    if bad=='overflow':p['overflow']['history']['dropped']=35
    if bad=='limit':p['overflow']['history']['record_limit']=50000
    if bad=='snapshot':history['snapshot_end_ns']=200000
    if bad=='abi':history['record_size']=64
    with pytest.raises(ValueError):validate(p)
