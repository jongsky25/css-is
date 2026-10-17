import io
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFont

import documents_dtrak as dtrak
import documents_reader as reader
import documents_page_reader as pages

SUBJECT = 'Submission of comments on the updated service guidelines for regional offices'


def fixture(scale=1, angle=0):
    image = Image.new('RGB', (1200, 1600), 'white')
    draw = ImageDraw.Draw(image); font = ImageFont.truetype('DejaVuSans.ttf', 23)
    draw.text((80, 140), 'DTRAK ROUTING SLIP', font=font, fill='black')
    for y in (350, 420, 490, 590, 690): draw.line((60, y, 1140, y), fill='black', width=3)
    for x in (60, 1140): draw.line((x, 350, x, 1000), fill='black', width=3)
    draw.text((70, 370), 'ORIGINATING OFFICE: Example Office', font=font, fill='black')
    draw.text((70, 440), 'TYPE OF DOCUMENT: Memorandum', font=font, fill='black')
    draw.text((70, 505), 'SUBJECT: Submission of comments on the updated', font=font, fill='black')
    draw.text((70, 540), 'service guidelines for regional offices', font=font, fill='black')
    draw.text((70, 620), 'DATE   FROM   TO   ACTION REQUIRED   DUE DATE', font=font, fill='black')
    transformed = image.resize((int(1200*scale), int(1600*scale))).rotate(angle, fillcolor='white')
    out = io.BytesIO(); transformed.save(out, 'JPEG', quality=65)
    image.close(); transformed.close(); return out.getvalue()


@pytest.mark.parametrize('scale,angle', [(1, 0), (.75, 0), (1, 1.5), (1, -1)])
def test_real_subject_cell_reading(scale, angle):
    result = dtrak.read_subject(fixture(scale, angle), 'DTRAK ROUTING SLIP')
    assert result['status'] == 'read', result
    assert result['value'] == SUBJECT
    assert result['preview'].startswith('data:image/jpeg;base64,')
    assert 'ACTION' not in result['value']


def test_successful_region_authoritative_over_later_page():
    reading = dict(status='read', method='dtrak_subject_cell', value=SUBJECT, raw=SUBJECT, reason='Check source')
    result = pages.summarize({'pages':[
        {'page':1,'text':'DTRAK ROUTING SLIP\nISUBJECT: damaged', 'ocr':True,'subject_reading':reading},
        {'page':2,'text':'Subject: Different later page', 'ocr':True}]})
    assert result['suggestions']['subject'] == SUBJECT
    assert result['evidence']['subject'][0]['page'] == 1
    assert result['field_readings']['subject'][0]['status'] == 'read'


def test_region_timeout_and_non_dtrak(monkeypatch):
    assert dtrak.read_subject(b'', 'Ordinary memorandum') is None
    def timeout(*args, **kwargs): raise subprocess.TimeoutExpired('tesseract', 4)
    monkeypatch.setattr(subprocess, 'run', timeout)
    result = dtrak.read_subject(fixture(), 'DTRAK ROUTING SLIP')
    assert result['status'] == 'failed' and not result['value']
    assert result['reason']


def test_invalid_metadata_rejected():
    with pytest.raises(ValueError):
        pages.summarize({'pages':[{'page':1,'text':'x','ocr':True,'subject_reading':{'status':'read','value':'x'*501}}]})


def test_layout_fallback_when_subject_label_is_missing(monkeypatch):
    original = dtrak._ocr
    def without_label(image, deadline, config='tsv'):
        text = original(image, deadline, config)
        if config == 'tsv':
            return '\n'.join(line for line in text.splitlines() if 'SUBJECT' not in line.upper())
        return text
    monkeypatch.setattr(dtrak, '_ocr', without_label)
    result = dtrak.read_subject(fixture(), 'DTRAK ROUTING SLIP')
    assert result['status'] == 'read'
    assert result['value'] == SUBJECT


def test_region_missing_is_distinct_from_empty_ocr():
    with Image.new('RGB', (1000, 1200), 'white') as image:
        out = io.BytesIO(); image.save(out, 'PNG')
    result = dtrak.read_subject(out.getvalue(), 'DTRAK ROUTING SLIP')
    assert result['status'] == 'region_not_found'
    assert result['raw'] == ''
