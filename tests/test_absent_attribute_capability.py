from copy import deepcopy
import pytest
from scripts.avatar_baseline.absent_attribute_capability import validate_receivers


def specimen():
    events=[];queries=[]
    for g,group in enumerate(['avatar','other']):
        for repeat in [0,1]:
            for kind in ['reference','census']:
                phase=f'{kind}:0:{group}:{repeat}';start=1000+len(queries)*1000
                queries.append({'phase':phase,'begin_ns':start,'end_ns':start+999,
                    'result':{'fixture_count':4096,'count':32,'values':[1]*32}})
                for i in range(32):
                    events.append({'kind':'reference' if kind=='reference' else 'receiver','phase':phase,
                        'address':hex(0x20010+g*1024+i*16),'begin_ns':start+i*3,
                        'callback_ready_ns':start+i*3+1,'returned_ns':start+i*3+2,
                        'attribute_absent':True if kind=='census' else None})
    return {'dom_before_sha256':'same','dom_after_sha256':'same','queries':queries,
            'native':{'build_id':'1c5dca8527a61d07372e489142bee26af1bcaf71','frida_version':'17.5.1',
                'pid':7,'identity_markers':[{'pid':7}],
                'agent_messages':[{'payload':{'ready':True,'pid':7}}],
                'history':{'dropped':0,'offsets':{'receiver':0x100cce80,'reference':0x100b1880},'events':events}}}


def test_getter_matches_known_reference_without_claiming_performance():
    r=validate_receivers(specimen())
    assert r['status']=='capability_passed' and r['null_native_returns']==128
    assert r['performance_qualified'] is False and r['acceptance'] is False


@pytest.mark.parametrize('failure',['missing','duplicate','wrong_receiver','not_null','dom','dropped','pid','query','outside'])
def test_receiver_and_absence_checks_fail_closed(failure):
    p=specimen();events=p['native']['history']['events']
    if failure=='missing':events.pop()
    if failure=='duplicate':events[1]['address']=events[0]['address']
    if failure=='wrong_receiver':events[32]['address']='0xdead'
    if failure=='not_null':events[32]['attribute_absent']=False
    if failure=='dom':p['dom_after_sha256']='changed'
    if failure=='dropped':p['native']['history']['dropped']=1
    if failure=='pid':p['native']['pid']=8
    if failure=='query':p['queries'][0]['result']['values'][0]=0
    if failure=='outside':events[0]['begin_ns']=1
    with pytest.raises(ValueError):validate_receivers(p)
