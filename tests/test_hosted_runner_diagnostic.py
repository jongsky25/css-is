from scripts.avatar_baseline.hosted_runner_diagnostic import mobile_summary


def test_phone_summary_preserves_failure_and_acceptance_limit():
    text=mobile_summary({'status':'diagnostic_failed','error':'one fixed control failed'})
    assert 'one fixed control failed' in text
    assert 'earlier failed calibration remains failed' in text
    assert 'does not accept 2B or deploy' in text
    assert 'avatar-runner-diagnostic' in text


def test_phone_summary_displays_all_controls_including_missing_cpu_context():
    result={'status':'hosted_diagnostic_complete','context':{'cohorts':[
        {'index':i,'duration_ms':3000+i,'system_steal_fraction':None if i==3 else .1} for i in range(4)]}}
    text=mobile_summary(result)
    assert '| 1 | 3000.00 | 10.00% |' in text
    assert '| 4 | 3003.00 | unavailable |' in text
    assert 'not an adjustment' in text
