import io
import re
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFont
import documents_page_reader as pages
import ocr_process
import storage as st


def page_image():
    with Image.new('RGB', (1500, 600), 'white') as image:
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('DejaVuSans.ttf', 40)
        draw.text((60, 80), 'Subject: Page selection test', fill='black', font=font)
        draw.text((60, 160), 'From: Training Office', fill='black', font=font)
        out = io.BytesIO(); image.save(out, 'JPEG'); return out.getvalue()


def test_real_image_ocr():
    assert 'Page selection test' in pages.read_image(page_image())['text']
    assert ocr_process._SLOT.acquire(blocking=False)
    ocr_process._SLOT.release()


def test_image_bounds_and_cleanup(monkeypatch):
    for raw in (b'', b'not an image', b'x' * (pages.MAX_IMAGE_BYTES + 1)):
        with pytest.raises(ValueError): pages.read_image(raw)
        assert ocr_process._SLOT.acquire(blocking=False)
        ocr_process._SLOT.release()
    with Image.new('RGB', (2001, 2000)) as image:
        out = io.BytesIO(); image.save(out, 'PNG')
    with pytest.raises(ValueError, match='pixels'): pages.read_image(out.getvalue())
    ocr_process._SLOT.acquire()
    try:
        with pytest.raises(ValueError, match='Another'): pages.read_image(page_image())
    finally: ocr_process._SLOT.release()


def test_aggregate_page_numbers_and_conflicts():
    result = pages.summarize({'pages': [
        {'page':7, 'text':'Subject: Staff orientation\nFrom: Training Office', 'ocr':True},
        {'page':3, 'text':'Department Order No. 2026-10', 'ocr':False}]})
    assert result['evidence']['subject'][0]['page'] == 7
    assert result['evidence']['type'][0]['page'] == 3
    assert result['reading']['ocr_pages'] == [7]
    assert [p['page'] for p in result['text_preview']] == [3,7]
    conflict = pages.summarize({'pages': [
        {'page':1, 'text':'Subject: First', 'ocr':False},
        {'page':2, 'text':'Subject: Second', 'ocr':True}]})
    assert 'subject' not in conflict['suggestions']
    assert any('Multiple values' in w for w in conflict['warnings'])


@pytest.mark.parametrize('payload', [None, {}, {'pages':[]}, {'pages':[None]},
    {'pages':[{'page':True,'text':'a','ocr':True}]}, {'pages':[{'page':501,'text':'a','ocr':True}]},
    {'pages':[{'page':1,'text':'x'*100001,'ocr':True}]},
    {'pages':[{'page':1,'text':'a','ocr':True}]*2},
    {'pages':[{'page':i+1,'text':'a','ocr':True} for i in range(51)]}])
def test_bad_aggregate(payload):
    with pytest.raises(ValueError): pages.summarize(payload)


def test_page_routes_auth_bounds_and_no_storage(app_mod, viewer, monkeypatch):
    conn=st.connect(app_mod.DB)
    old=st.get_setting(conn,'documents.enabled','0');st.set_setting(conn,'documents.enabled','1')
    tables=('document','document_sequence','document_file_version','document_job','document_event','ai_interaction')
    counts={t:conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
    try:
        page=viewer.get('/documents/new')
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        monkeypatch.setattr(pages,'read_image',lambda raw, **kwargs:{'text':'Subject: One page'})
        assert viewer.post('/documents/intake/page',content=page_image(),headers={'content-type':'image/jpeg'}).status_code==403
        headers={'content-type':'image/jpeg','x-csrf-token':csrf}
        response=viewer.post('/documents/intake/page',content=page_image(),headers=headers)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert viewer.post('/documents/intake/page',content=b'x'*(pages.MAX_IMAGE_BYTES+1),headers=headers).status_code==400
        response=viewer.post('/documents/intake/pages-result',json={'pages':[{'page':12,'text':response.json()['text'],'ocr':True}]},headers={'x-csrf-token':csrf})
        assert response.status_code==200
        assert response.json()['evidence']['subject'][0]['page']==12
        assert response.headers['cache-control']=='no-store'
        assert counts=={t:conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
    finally:
        st.set_setting(conn,'documents.enabled',old);conn.close()
