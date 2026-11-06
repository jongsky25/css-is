import pytest
import documents_understanding as understanding
from test_documents_understanding import first_request


@pytest.mark.parametrize('month,number',[('Jan',1),('Feb',2),('Mar',3),('Apr',4),('May',5),('Jun',6),('Jul',7),('Aug',8),('Sep',9),('Sept',9),('Oct',10),('Nov',11),('Dec',12)])
@pytest.mark.parametrize('style',['day_first','month_first','period','wrapped'])
def test_abbreviations_keep_literal_evidence(month,number,style):
    if style=='day_first': value=f'20 {month} 2026'
    elif style=='month_first': value=f'{month.upper()} 20, 2026'
    elif style=='period': value=f'20 {month}. 2026' if month!='May' else '20 May 2026'
    else: value=f'{month}.\n20, 2026' if month!='May' else 'May\n20, 2026'
    request=first_request('Please submit comments by '+value+' via email. Please nominate a representative.')
    assert request['deadline']==f'2026-{number:02d}-20'
    assert request['detail_evidence']['deadline'] in request['evidence']
    assert request['submission']=='via email'
    assert 'nominate' not in request['evidence']


@pytest.mark.parametrize('value', ['29 Feb. 2026','31 Apr. 2026','Nov. 20','Nov. 20, 26','20 N0v. 2026',
    '20 Nov. 2026 or 25 Nov. 2026','20 Nov. 2026–25 Nov. 2026','20 Nov. 2026; deadline: 21 Nov. 2026',
    '11/12/2026','next Friday','20 Nov. 2026/2027'])
def test_ambiguous_invalid_and_conflicting_abbreviations_stay_blank(value):
    request=first_request('Please submit comments by '+value+'.')
    assert request['deadline']=='' and request['warnings']


def test_event_date_does_not_become_deadline_and_requests_stay_separate():
    result=understanding.suggest(['Please attend on Nov. 20, 2026. Please submit comments by Dec. 1, 2026.'])
    assert len(result['requests'])==2
    assert result['requests'][0]['deadline']==''
    assert result['requests'][1]['deadline']=='2026-12-01'
    assert 'Nov. 20' in result['requests'][0]['evidence']


def test_repeated_identical_abbreviated_deadline_and_submission_boundary():
    request=first_request('Please submit comments via email by 20 Nov. 2026 (deadline: November 20, 2026).')
    assert request['deadline']=='2026-11-20'
    assert request['submission']=='via email'


def test_period_protection_does_not_merge_paragraphs_or_incomplete_dates():
    assert len(list(understanding._sentences('Please submit by Nov.\n\n20, 2026.')))==2
    assert len(list(understanding._sentences('Please submit by Nov. Please nominate someone.')))==2


def test_leap_day_and_multiple_requests_in_one_sentence():
    result=understanding.suggest(['Please submit comments by Feb. 29, 2024 and kindly provide reports by Mar. 1, 2024.'])
    assert [r['deadline'] for r in result['requests']]==['2024-02-29','2024-03-01']


def test_drive_and_local_reader_share_abbreviated_date_evidence():
    import documents_operations as operations
    from documents_page_reader import summarize
    passage='Please submit health financing comments by 20 Nov. 2026.'
    local=summarize({'pages':[{'page':1,'text':passage,'ocr':True}]})['understanding']['requests'][0]
    remote=operations.sanitize_extraction({'suggestions':{},'understanding_text':passage})['understanding']['requests'][0]
    assert local['deadline']==remote['deadline']=='2026-11-20'
    assert local['detail_evidence']['deadline']==remote['detail_evidence']['deadline']=='by 20 Nov. 2026'
