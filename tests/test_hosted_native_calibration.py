from scripts.avatar_baseline.hosted_native_calibration import summary


def test_passing_instrument_does_not_claim_application_acceptance():
    text=summary({'status':'calibration_passed','instrument_qualified_for_application_calibration':True,
        'calibration_audit':{'errors':[],'cohorts':[{'index':i,'mode':m,'duration_ms':3000+i,
            'observation_fraction_bound':.03} for i,m in enumerate(['control','probe','probe','control'])]}})
    assert 'All frozen instrument gates passed' in text and 'separately frozen protocol' in text
    assert 'does not accept 2B' in text and '| 4 | control |' in text
    assert 'avatar-native-calibration' in text


def test_failed_gate_remains_a_failure_with_no_automatic_followup():
    text=summary({'status':'calibration_failed','instrument_qualified_for_application_calibration':False,
        'calibration_audit':{'errors':['Controls vary more than 20%'],'cohorts':[]}})
    assert 'Controls vary more than 20%' in text and 'not qualified' in text
    assert 'no automatic retry or application comparison' in text


def test_prerequisite_failure_can_be_shown_before_any_slot_exists():
    text=summary({'status':'calibration_failed','instrument_qualified_for_application_calibration':False,
                  'error':'native-preflight failed; later phases not launched'})
    assert 'later phases not launched' in text and 'not qualified' in text
