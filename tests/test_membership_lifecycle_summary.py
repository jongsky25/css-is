from scripts.avatar_baseline.summarize_membership_lifecycle import native_periods


def specimen(pool_begin):
    def event(kind, address, begin, phase='navigation:0'):
        return {'kind':kind,'backend':'0x10' if kind != 'receiver' else None,'address':hex(address),
                'begin_ns':begin,'callback_ready_ns':begin+1,'returned_ns':begin+2,'phase':phase}
    p={'begin_ns':0,'end_ns':500000,'pid':7,
       'before':{'name':'a','begin_ns':1000,'end_ns':2000},
       'after':{'name':'b','begin_ns':501000,'end_ns':502000},
       'history':{'events':[event('allocate',0x20000,10000),
                           event('receiver',0x20010,20000,'census:0:avatar:0'),
                           event('pool',0x20000,pool_begin)]}}
    trace={'traceEvents':[{'name':'clock_sync','ts':1,'args':{'sync_id':'a'}},
                          {'name':'clock_sync','ts':501,'args':{'sync_id':'b'}},
                          {'name':'CppGC.IncrementalSweep','pid':7,'tid':7,'ts':290,'dur':30,'ph':'X','args':{}}]}
    return p,trace


def test_postwindow_return_cannot_become_measured_reclamation_or_gc_correlation():
    result=native_periods(*specimen(700000))
    assert result['native_counts_by_period']['after']['pool']==1
    assert result['labelled_returned_generations_inside']==0
    assert result['labelled_returned_generations_outside']==1
    assert result['labelled_returns'][0]['sweep_overlap'] is None


def test_inside_return_matches_prior_label_and_observed_sweep():
    result=native_periods(*specimen(300000))
    assert result['labelled_returned_generations_inside']==1
    assert result['labelled_returns'][0]['documents_observed']==[0]
    assert result['labelled_returns'][0]['groups_observed']==['avatar']
    assert len(result['labelled_returns'][0]['sweep_overlap'])==1


def test_boundary_straddling_is_retained_and_does_not_pass_within_window():
    result=native_periods(*specimen(499999))
    assert result['native_counts_by_period']['straddling']['pool']==1
    assert result['labelled_returned_generations_inside']==0
