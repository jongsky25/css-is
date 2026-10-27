import copy
import pytest
from scripts.avatar_baseline.analyze_page_history import history_summary,timing_gate


def fixture():
    def e(kind,t,page='0x1000'):
        return {'kind':kind,'begin_ns':t,'callback_ready_ns':t+1,'returned_ns':t+2,
                'page':page,'backend':'0x1','stack':[]}
    return {'dropped':0,'offsets':{'allocate':0x5ab0350,'pool':0x5ab0550},
            'events':[e('pool',10,'0x2000'),e('allocate',20),e('pool',30),e('allocate',40)]}


def test_lifetimes_distinguish_observed_reuse_and_unknown_initial_pages():
    result=history_summary(fixture(),1,100)
    assert result['allocation_requests']==2 and result['pool_returns']==2
    assert result['observed_reuses']==1
    assert result['preexisting_or_unobserved_pool_returns']==1


@pytest.mark.parametrize('edit,match', [
    (lambda h:h.update(dropped=1),'Dropped'),
    (lambda h:h['events'].append({**h['events'][-1],'begin_ns':50,'callback_ready_ns':51,'returned_ns':52}),'Duplicate active'),
    (lambda h:h['events'][0].update(page='0x0'),'Null pool'),
    (lambda h:h['events'][1].update(callback_ready_ns=999),'Invalid native'),
])
def test_invalid_history_fails_closed(edit,match):
    h=fixture();edit(h)
    with pytest.raises(ValueError,match=match):history_summary(h,1,100)


def test_overhead_gate_preserves_both_orders_control_and_explicit_costs():
    rows=[{'index':i,'status':'valid','navigation_ms':1000} for i in range(4)]
    assert timing_gate(rows)==[]
    changed=copy.deepcopy(rows);changed[2]['navigation_ms']=1201
    assert timing_gate(changed)==['Probe/control duration exceeds 1.20: 3/2']
    changed=copy.deepcopy(rows);changed[3]['navigation_ms']=1201
    assert 'Control duration varies more than 20%' in timing_gate(changed)
    changed=copy.deepcopy(rows);changed[1]['history']={'explicit_preparation_fraction':.051,'maximum_preparation_ms':1}
    assert any('5% or 250ms' in s for s in timing_gate(changed))
    assert timing_gate(rows[:3])==['Require four intact slots']
