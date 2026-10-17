"""Bounded, transient page-image OCR and aggregation for browser PDF selection."""
import io
import subprocess

from PIL import Image
import documents_ocr
import documents_reader

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
MAX_RESULT_BYTES = 650_000
MAX_PAGES = 50


def read_image(raw):
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError('A page image must be no larger than 2 MiB.')
    if not documents_ocr._LOCK.acquire(blocking=False):
        raise ValueError('Another page is being read. Retry this page shortly.')
    try:
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('JPEG', 'PNG') or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError('Use a JPEG or PNG page image with at most 4 million pixels.')
                image.load()
                with image.convert('RGB') as rgb, io.BytesIO() as output:
                    rgb.save(output, format='PNG')
                    png = output.getvalue()
        except ValueError:
            raise
        except Exception:
            raise ValueError('This page image could not be opened. Retry the page.') from None
        try:
            result = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '3',
                                     '-c', 'debug_file=/dev/null'], input=png,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    timeout=15, check=True)
        except FileNotFoundError:
            raise ValueError('OCR is unavailable on this server. Try again later.') from None
        except subprocess.TimeoutExpired:
            raise ValueError('OCR timed out on this page. Retry it or choose another page.') from None
        except subprocess.CalledProcessError:
            raise ValueError('OCR failed on this page. Retry it or choose another page.') from None
        text = result.stdout.decode('utf-8', errors='replace').strip()
        if not text:
            raise ValueError('No readable text was found on this page. Try a clearer copy.')
        if len(text) > documents_reader.MAX_TEXT:
            raise ValueError('This page contains too much text.')
        return {'text': text}
    finally:
        documents_ocr._LOCK.release()


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
    result = documents_reader.suggest([item['text'] for item in pages])
    for evidence in result['evidence'].values():
        for item in evidence:
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
