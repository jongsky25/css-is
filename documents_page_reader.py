"""Bounded transient OCR and aggregation for browser PDF page selection."""
from ocr_process import MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, read
import documents_reader

MAX_RESULT_BYTES = 650_000
MAX_PAGES = 50


def read_image(raw, *, cancelled=None):
    return read(raw, mode='image', cancelled=cancelled)


async def read_image_async(raw, *, disconnected=None):
    return await documents_reader.read_in_thread(read_image, raw, disconnected=disconnected)


def summarize(payload):
    pages = payload.get('pages') if isinstance(payload, dict) else None
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES:
        raise ValueError('Review between 1 and 50 completed pages.')
    seen, total = set(), 0
    for item in pages:
        if not isinstance(item, dict):
            raise ValueError('Invalid page reading.')
        number, text, ocr = item.get('page'), item.get('text'), item.get('ocr')
        if type(number) is not int or not 1 <= number <= 500 or number in seen:
            raise ValueError('Page numbers must be unique and between 1 and 500.')
        if not isinstance(text, str) or type(ocr) is not bool:
            raise ValueError('Invalid page reading.')
        total += len(text)
        if total > documents_reader.MAX_TEXT:
            raise ValueError('The selected pages contain too much text. Clear the reading and select fewer pages.')
        seen.add(number)
    pages = sorted(pages, key=lambda item: item['page'])
    subjects = {}
    for i, item in enumerate(pages):
        reading = item.get('subject_reading')
        if reading is None: continue
        if not isinstance(reading, dict): raise ValueError('Invalid subject reading.')
        cleaned = {}
        for key, limit in [('status', 30), ('method', 40), ('value', 500), ('raw', 1500), ('reason', 300)]:
            value = reading.get(key, '')
            if not isinstance(value, str) or len(value) > limit: raise ValueError('Invalid subject reading.')
            cleaned[key] = value
        if cleaned['status'] not in ('read', 'empty', 'rejected', 'failed', 'region_not_found') or cleaned['method'] != 'dtrak_subject_cell':
            raise ValueError('Invalid subject reading.')
        subjects[i] = cleaned
    result = documents_reader.suggest([item['text'] for item in pages], subjects)
    for reading in result.get('field_readings', {}).get('subject', []):
        reading['page'] = pages[reading['page'] - 1]['page']
    for evidence in result['evidence'].values():
        for item in evidence:
            item['page'] = pages[item['page'] - 1]['page']
    for candidates in result.get('conflicts', {}).values():
        for item in candidates:
            item['page'] = pages[item['page'] - 1]['page']
    ocr_pages = [item['page'] for item in pages if item['ocr']]
    result['scope'] = 'selected_pages'
    result['reading'] = {'page_count': len(pages), 'ocr_pages': ocr_pages}
    result['text_preview'] = [{'page': item['page'], 'text': item['text'][:2000],
                               'truncated': len(item['text']) > 2000} for item in pages[:10]]
    result['preview_truncated'] = len(pages) > 10
    result['warnings'].insert(0, 'Only completed selected pages were read. Other pages may contain relevant details.')
    if ocr_pages:
        result['warnings'].append('OCR was used; check names, numbers and dates against the scan.')
    return result
