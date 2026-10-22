"""Independent reference arithmetic for sparse, categorical and damaged answers."""
import pandas as pd
import pytest
import css_is_engine as eng
import dashboard_insights as di


@pytest.fixture(params=[False, True], ids=['object-items', 'categorical-items'])
def reference(request):
    # B1 mean=(7+3)/2=5; B2=5 -> Reliability=5; Responsiveness=3.
    # Overall=(5+3)/2=4, with TWO contributing people. No other dimensions.
    rows = [(1, 'B1', 7, False), (2, 'B1', 3, False),
            (1, 'B2', 5, False), (1, 'B5', 3, False),
            (3, 'B6', float('nan'), False), (4, 'B7', float('inf'), False),
            (5, 'B8', 'broken', False), (6, 'B9', 0, True),
            (7, 'B9', 8, False), (8, 'B9', None, False)]
    frame = pd.DataFrame(rows, columns=['response_id', 'item_id', 'value', 'is_na'])
    frame['form_instance_id'] = 100
    frame['survey_type'] = 2
    frame['org_path'] = 'BLHSD/TEST'
    frame['event_date'] = '2026-01-01'
    if request.param:
        frame['item_id'] = pd.Categorical(frame.item_id, categories=['A', *eng.SERVQUAL_ITEMS, 'C', 'SQD1'])
    return frame


def test_reference_counts_means_and_fast_paths(reference):
    original = reference.copy(deep=True)
    _, _, counts = eng.answer_quality(reference)
    assert counts == {'valid': 4, 'na': 1, 'invalid': 5}
    metric = eng.overall_perception(reference, eng.DIM_MAP_FORM2)
    assert (metric.value, metric.n, metric.flags) == (4, 2, ['low n'])
    dim = eng.dimension_mean(reference, ['B1', 'B2'])
    assert (dim.value, dim.n) == (5, 3)
    assert eng.item_stats(reference, 'B1')['n'] == 2
    assert eng.item_stats(reference, 'B6') is None
    assert eng.quality_index(reference) == pytest.approx((50, 2))
    assert di.event_overall_map(reference, eng.DIM_MAP_FORM2) == {100: 4}
    report = di.activity_servqual(reference, [100])
    assert report['average'] == 4 and report['respondents'] == 2
    assert report['expectation'] is None and report['servqual'] is None
    assert report['osq'] is None
    assert {d['key']: d['value'] for d in report['dims']} == {'Reliability': 5, 'Responsiveness': 3}
    pd.testing.assert_frame_equal(reference, original)


def test_all_unrated_is_absent_not_zero_or_nan(reference):
    frame = reference.iloc[4:]
    assert eng.overall_perception(frame, eng.DIM_MAP_FORM2).value is None
    assert eng.dimension_mean(frame, ['B6', 'B7']).value is None
    assert eng.quality_index(frame) == (None, 0)
    assert di.activity_servqual(frame, [100]) is None
    assert di.event_overall_map(frame, eng.DIM_MAP_FORM2) == {}


def test_arta_denominator_and_distribution():
    frame = pd.DataFrame({'item_id': ['SQD1'] * 8, 'response_id': range(8),
                          'value': [5, 4, 2, None, float('inf'), 'oops', 6, 0],
                          'is_na': [False] * 7 + [True]})
    m = eng.arta_topbox(frame)
    assert m.n == 3 and m.value == pytest.approx(200/3)
    d = eng.arta_item_detail(frame, 'SQD1')
    assert (d['n'], d['na'], d['invalid']) == (3, 1, 4)
    assert sum(d['dist'].values()) == 3


def test_missing_scope_and_nonfinite_trend():
    frame = pd.DataFrame({'org_path': [None, pd.NA, 'BLHSD/TEST', 'OTHER']})
    assert eng.scope(frame, org_prefix='BLHSD').index.tolist() == [2]
    bad = [None, pd.NA, float('nan'), float('inf'), -float('inf'), 'oops']
    assert di.consistency(bad)['known'] is False
    assert di.stability_phrase([{'value': x} for x in bad])['tone'] == 'neutral'
    assert di.consistency([6, *bad, 6])['sd'] == 0
    assert di.stability_phrase([{'value': x} for x in [6, *bad, 6]])['phrase'] == 'Holding steady.'
    assert di._servqual_verdict(float('nan')) is None


def test_reference_official_report_and_exports(reference, app_mod, monkeypatch):
    import io
    import re
    from zipfile import ZipFile
    from openpyxl import load_workbook
    from pypdf import PdfReader
    import report_docs
    monkeypatch.setattr(app_mod.st, 'demographics_for_responses', lambda *a: {})
    monkeypatch.setattr(app_mod.st, 'response_context_for_ids', lambda *a: {})
    report = app_mod._servqual_official(reference, eng.DIM_MAP_FORM2, [], None)
    assert report['overall']['value'] == 4
    assert report['overall']['n'] == 2
    assert report['respondents'] == 8  # submitted people, separate from rated people
    assert report['answer_quality'] == {'valid': 4, 'na': 1, 'invalid': 5}
    assert report['summary']['average'] == '4.00'
    assert report['summary']['total'] == '8.00'
    assert len(report['responses']) == 8  # retain six unrated submissions with blank scores
    assert [r['overall'] for r in report['responses']] == [4.5, 3, None, None, None, None, None, None]
    meta = {'title': 'Reference report', 'scope': 'Synthetic', 'generated': '2026-01-01'}
    for fmt in ('xlsx', 'docx', 'pptx', 'pdf'):
        data = getattr(report_docs, f'servqual_{fmt}')(report, meta)
        if fmt == 'xlsx':
            wb = load_workbook(io.BytesIO(data))
            assert wb['Summary']['B6'].value == '4.00'
            assert wb['Dimensions']['C4'].value == 5
            assert wb['Dimensions']['C5'].value == 3
            text = ' '.join(str(c.value) for ws in wb for row in ws for c in row)
        elif fmt == 'pdf':
            text = ' '.join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
        else:
            with ZipFile(io.BytesIO(data)) as z:
                names = ['word/document.xml'] if fmt == 'docx' else [n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+.xml', n)]
                text = ' '.join(z.read(n).decode() for n in names)
        assert '4.00' in text
        assert not re.search(r'\b(?:nan|inf|-inf)\b', text, re.I)


def test_no_ratings_does_not_claim_success(app_mod):
    event = {'name': 'Unrated reference activity', 'date': '2026-01-01', 'respondents': 0}
    profile = app_mod._activity_mrr_profile(event)
    assert 'no valid dimension ratings' in app_mod._mrr_action_text(profile)
    assert 'cannot be assessed' in app_mod._mrr_resources_text(profile)
    assert 'collect valid dimension ratings' in app_mod._mrr_next_steps_text(profile, event)


def test_report_html_distinguishes_submissions_and_scored_people(reference, admin, app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, 'get_atoms', lambda *a, **k: eng.assign_periods(reference))
    response = admin.get('/reports?type=2')
    assert response.status_code == 200
    assert '2 rated respondent(s)' in response.text
    assert '8 total submission(s)' in response.text
    assert '5 missing or invalid answer(s)' in response.text
    assert '4.00' in response.text
