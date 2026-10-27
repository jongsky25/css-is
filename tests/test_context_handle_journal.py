import copy
import pytest
from scripts.avatar_baseline.context_handle_journal import analyze, OFFSETS
from scripts.avatar_baseline.element_membership_lifecycle import BUILD


def fixture():
    def event(number,kind,begin,end,parent=0,**values):
        return dict(id=number,kind=kind,begin_ns=begin,end_ns=end,thread=1,parent=parent,**values)
    events=[event(1,'state_ctor',10,90,owner='0x10'),
        event(2,'global_create',20,21,1,owner='0x10',slot='0x100'),
        event(3,'per_ctor',30,80,1,owner='0x20'),
        event(4,'global_create',40,41,3,owner='0x20',slot='0x200'),
        event(5,'global_weak_field',82,84,1,creation=2,slot='0x100'),
        event(6,'state_dispose',100,150,owner='0x10'),
        event(7,'global_weak_field',110,111,6,creation=4,slot='0x200'),
        event(8,'global_release',120,121,6,creation=2,slot='0x100'),
        event(9,'extension_invalidate',160,161,owner='0x30'),
        event(10,'gc_epilogue',200,201,owner='0x40')]
    journal={'native':dict(protocol='context-handle-journal-v1',pid=123,offsets=OFFSETS,
        clock_domain='CLOCK_MONOTONIC',dropped=0,pending=0,snapshot_requested=False,gc_requested=False,events=events),
        'clock_samples':[dict(begin_ns=1,native_ns=2,end_ns=3)]*20,'messages':[],
        'export_end_ns':1000,'cdp_events':[]}
    capture={'pid':123,'build_id':BUILD,'stages':[dict(index=0,begin_ns=1,end_ns=170),dict(index=1,begin_ns=171,end_ns=300)]}
    return journal,capture


def test_disposed_and_weakened_context_is_not_a_strong_root():
    journal,capture=fixture()
    result=analyze(journal,capture)
    assert result['instrument_qualified'] is False
    assert result['gc_epilogues'][0]['known_strong_context_handles']==[]


def test_missing_owner_weakening_identifies_old_known_root():
    journal,capture=fixture()
    journal['native']['events'][6]['kind']='state_dissociate'
    row=analyze(journal,capture)['gc_epilogues'][0]['old_known_strong_context_handles']
    assert len(row)==1 and row[0]['role']=='V8PerContextData::context_' and row[0]['created_stage']==0


@pytest.mark.parametrize('mutation',['clock','dropped','pending','pid','build','offset','parent','after_release','generation'])
def test_reject_ambiguous_or_incomplete_journal(mutation):
    journal,capture=fixture()
    journal=copy.deepcopy(journal)
    if mutation=='clock':journal['clock_samples'][0]['native_ns']=4
    if mutation=='dropped':journal['native']['dropped']=1
    if mutation=='pending':journal['native']['pending']=1
    if mutation=='pid':capture['pid']=999
    if mutation=='build':capture['build_id']='wrong'
    if mutation=='offset':journal['native']['offsets']['global_release']+=1
    if mutation=='parent':journal['native']['events'][3]['parent']=9
    if mutation=='after_release':
        journal['native']['events'][7]['kind']='global_weak_direct'
        journal['native']['events'][4]['kind']='global_release'
    if mutation=='generation':journal['native']['events'][7]['creation']=4
    with pytest.raises(ValueError):analyze(journal,capture)


def test_reused_slot_gets_a_distinct_owner_generation():
    journal,capture=fixture()
    events=journal['native']['events']
    events.extend([dict(id=11,kind='state_ctor',begin_ns=210,end_ns=260,thread=1,parent=0,owner='0x10'),
        dict(id=12,kind='global_create',begin_ns=220,end_ns=221,thread=1,parent=11,owner='0x10',slot='0x100'),
        dict(id=13,kind='gc_epilogue',begin_ns=270,end_ns=271,thread=1,parent=0,owner='0x40')])
    rows=analyze(journal,capture)['gc_epilogues']
    assert rows[0]['known_strong_context_handles']==[]
    assert rows[1]['known_strong_context_handles'][0]['creation']==12
    assert rows[1]['old_known_strong_context_handles']==[]
