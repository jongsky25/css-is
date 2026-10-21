"""Image/PDF work imported only after the OCR child applies resource limits."""
import io
import math
import subprocess
import time

from PIL import Image
import ocr_tesseract

MAX_OCR_PAGES = 10
MAX_PIXELS = 12_000_000
MAX_TEXT = 100_000
ERROR_CODES = {'bytes', 'image_bytes', 'image', 'pages', 'size', 'text', 'empty',
               'resource', 'timeout', 'unavailable', 'unreadable'}


def page_text(png, deadline):
    try:
        text = ocr_tesseract.run(png, deadline).decode('utf-8', errors='replace').strip()
    except FileNotFoundError:
        raise ValueError('unavailable') from None
    except subprocess.TimeoutExpired:
        raise ValueError('timeout') from None
    except subprocess.CalledProcessError:
        raise ValueError('unreadable') from None
    if len(text) > MAX_TEXT:
        raise ValueError('text')
    text = routing_deadline(png, text, deadline - time.monotonic())
    subject = None
    if deadline - time.monotonic() >= 8:
        from documents_dtrak import read_subject
        subject = read_subject(png, text, deadline=deadline)
    if len(text) > MAX_TEXT:
        raise ValueError('text')
    return text, subject


def render(page):
    width, height = page.get_size()
    if not all(math.isfinite(v) and 0 < v <= 14400 for v in (width, height)):
        raise ValueError('size')
    scale = min(200 / 72, math.sqrt(MAX_PIXELS / (width * height)) * .99)
    bitmap = page.render(scale=scale)
    try:
        if bitmap.width * bitmap.height > MAX_PIXELS:
            raise ValueError('size')
        image = bitmap.to_pil()
        try:
            with io.BytesIO() as buffer:
                image.save(buffer, format='PNG')
                return buffer.getvalue()
        finally:
            image.close()
    finally:
        bitmap.close()


def extract(raw, config):
    deadline = time.monotonic() + config['seconds']
    if config['mode'] == 'image':
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('JPEG', 'PNG') or image.width * image.height > 4_000_000:
                    raise ValueError('image')
                image.load()
                with image.convert('RGB') as rgb, io.BytesIO() as output:
                    rgb.save(output, format='PNG')
                    png = output.getvalue()
        except ValueError:
            raise
        except Exception:
            raise ValueError('unreadable') from None
        text, subject = page_text(png, deadline)
        if not text:
            raise ValueError('empty')
        return {'text': text, 'subject_reading': subject}
    if not raw.startswith(b'%PDF-'):
        raise ValueError('unreadable')
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(raw)
    try:
        indices = config['indices']
        if not 1 <= len(document) <= 50 or not 1 <= len(indices) <= MAX_OCR_PAGES or any(not 0 <= i < len(document) for i in indices):
            raise ValueError('pages')
        pages, subjects, total = {}, {}, 0
        for index in indices:
            if deadline <= time.monotonic():
                raise ValueError('timeout')
            page = document[index]
            try:
                png = render(page)
            finally:
                page.close()
            text, subject = page_text(png, deadline)
            total += len(text)
            if total > MAX_TEXT:
                raise ValueError('text')
            pages[str(index)] = text
            if subject is not None:
                subjects[str(index)] = subject
        return {'pages': pages, 'subjects': subjects}
    finally:
        document.close()


def routing_deadline(png, text, timeout=5):
    """Optional bounded positional pass; only dates beneath the DUE DATE column."""
    import csv
    import re
    if not ('DTRAK' in text.upper() and 'ORIGINATING OFFICE' in text.upper()):
        return text
    try:
        from PIL import Image
        with Image.open(io.BytesIO(png)) as image, io.BytesIO() as buffer:
            image.thumbnail((1200, 1700))
            image.save(buffer, format='PNG')
            table_png = buffer.getvalue()
        output = ocr_tesseract.run(table_png, time.monotonic() + max(.1, timeout),
                                   seconds=5, psm='6', config='tsv')
        words = []
        for row in csv.DictReader(io.StringIO(output.decode('utf-8')), delimiter='\t', quoting=csv.QUOTE_NONE):
            if row.get('level') != '5' or float(row['conf']) < 55:
                continue
            words.append((row['text'].strip('|{}[]'), int(row['left']), int(row['top']), int(row['width']), int(row['height'])))
        # Recover a standalone tracking caption missed by the layout-oriented pass.
        tracking = {word for word, x, y, w, h in words if re.fullmatch(r'20\d{2}-\d{6,12}', word)}
        if len(tracking) == 1 and not re.search(r'^20\d{2}-\d{6,12}$', text, re.M):
            text = next(iter(tracking)) + '\n' + text
        dates = set()
        for word, x, y, w, h in words:
            if word.upper() != 'DUE':
                continue
            partners = [item for item in words if item[0].upper() == 'DATE' and
                        abs(item[2]-y) < max(h, item[4]) and 0 < item[1]-x < w*4]
            if len(partners) != 1:
                continue
            right = partners[0][1] + partners[0][3]
            for value, dx, dy, dw, dh in words:
                if re.fullmatch(r'20\d{2}-\d{2}-\d{2}', value) and y+h < dy < y+h*14:
                    # Date centre must align with this header, never the DATE column.
                    if x-w/2 <= dx+dw/2 <= right+w/2:
                        from documents_reader import _date
                        if _date(value): dates.add(value)
        if len(dates) == 1:
            return text + '\nDeadline: ' + next(iter(dates))
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        pass  # Keep successful header OCR if the optional table pass fails.
    return text
