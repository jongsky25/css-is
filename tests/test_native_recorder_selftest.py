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
            'storage':{'state_bytes':7200088,'allocated_bytes':7200256,'first_protection':None,'last_protection':None,'canary_verified':True,'check':'two-way-owned-buffer-canary'}}}
    return p


def test_complete_clock_concurrency_and_overflow_proof():
    result=validate(specimen())
    assert result['status']=='selftest_passed' and result['immutable_records']==1024
    assert result['overflow_stored']==32 and result['overflow_dropped']==36
    assert result['acceptance'] is False


@pytest.mark.parametrize('bad',['clock','records','threads','duplicate','pointer','phase','pending','overflow','limit','snapshot','abi','canary'])
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
    if bad=='canary':history['storage']['canary_verified']=False
    with pytest.raises(ValueError):validate(p)


def live_specimen():
    p=specimen()['concurrency']['history']
    p['address_encoding']='native-u64-buffer-v1'
    p['events']=[{'kind':'receiver','thread':101,'begin_ns':1000,'callback_ready_ns':1001,
                  'returned_ns':1002,'phase_type':1,'phase_document':0,'receiver_group':0,
                  'phase':'census:0:avatar:0'}]
    return p


def test_live_buffer_accepts_only_completed_native_snapshot():
    from scripts.avatar_baseline.native_recorder_selftest import validate_live
    validate_live(live_specimen(),[89999,90001])


@pytest.mark.parametrize('bad',['fake','phase','group','clock','snapshot','pending','drop','encoding'])
def test_live_buffer_rejects_invalid_measurement(bad):
    from scripts.avatar_baseline.native_recorder_selftest import validate_live
    p=live_specimen();e=p['events'][0]
    if bad=='fake':e['kind']='__selftest'
    if bad=='phase':e['phase']='navigation:0'
    if bad=='group':e['receiver_group']=4
    if bad=='clock':e['returned_ns']=90001
    if bad=='snapshot':p['snapshot_end_ns']=90002
    if bad=='pending':p['pending_at_snapshot']=1
    if bad=='drop':p['dropped']=1
    if bad=='encoding':p['address_encoding']='deferred-native-pointer-v1'
    with pytest.raises(ValueError):validate_live(p,[89999,90001])


def test_versioned_lifecycle_sources_preserve_old_agents():
    from scripts.avatar_baseline.analyze_membership_lifecycle import sources_for
    assert sources_for('native-membership-lifecycle-v6')[1].endswith('/element_membership_lifecycle.js')
    assert sources_for('native-membership-lifecycle-v11')[1].endswith('/absent_attribute_membership.js')
    assert sources_for('native-membership-lifecycle-v12')[1].endswith('/callback_buffer.js')
    assert [len(sources_for(f'native-membership-lifecycle-v{i}')) for i in [6,11,12]]==[6,7,8]
