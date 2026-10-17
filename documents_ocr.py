"""Local OCR using memory-only PDF rendering and Tesseract stdin/stdout pipes."""
import io
import math
import subprocess
import threading
import time

MAX_OCR_PAGES = 10
MAX_PIXELS = 12_000_000
OCR_SECONDS = 45
# PDFium is not thread safe. Bound concurrent rasterization and OCR memory use.
_LOCK = threading.Lock()


class PageReadings(dict):
    """Text mapping with transient field evidence; callers may still use it as a dict."""
    def __init__(self):
        super().__init__()
        self.subjects = {}


def read_pages(raw, indices):
    if len(indices) > MAX_OCR_PAGES:
        raise ValueError('This PDF needs OCR on more than 10 pages. Split it into smaller PDFs or enter the details manually.')
    if not _LOCK.acquire(blocking=False):
        raise ValueError('Another scanned PDF is being read. Try again shortly or continue manually.')
    try:
        import pypdfium2 as pdfium
        deadline = time.monotonic() + OCR_SECONDS
        document = pdfium.PdfDocument(raw)
        try:
            result = PageReadings()
            for index in indices:
                if time.monotonic() >= deadline:
                    raise ValueError('Reading the scanned PDF timed out. Try fewer pages or continue manually.')
                page = document[index]
                try:
                    width, height = page.get_size()
                    if not all(math.isfinite(v) and 0 < v <= 14400 for v in (width, height)):
                        raise ValueError('This PDF has an unsupported page size. Continue manually.')
                    # 200 dpi, reduced for large sheets to keep memory bounded.
                    scale = min(200 / 72, math.sqrt(MAX_PIXELS / (width * height)) * .99)
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil()
                        try:
                            with io.BytesIO() as buffer:
                                image.save(buffer, format='PNG')
                                png = buffer.getvalue()
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('Reading the scanned PDF timed out. Try fewer pages or continue manually.')
                try:
                    # No shell, filename, temporary directory or output artifact.
                    # Explicit output configuration also disables Tesseract's debug file.
                    completed = subprocess.run(
                        ['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '3',
                         '-c', 'debug_file=/dev/null'],
                        input=png, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        timeout=min(15, remaining), check=True)
                except FileNotFoundError:
                    raise ValueError('OCR is unavailable on this server. Continue manually.') from None
                except subprocess.TimeoutExpired:
                    raise ValueError('Reading the scanned PDF timed out. Try fewer pages or continue manually.') from None
                except subprocess.CalledProcessError:
                    raise ValueError('The scanned page could not be read. Continue manually.') from None
                result[index] = routing_deadline(png, completed.stdout.decode('utf-8', errors='replace').strip(), deadline-time.monotonic())
                if deadline-time.monotonic() >= 8:
                    from documents_dtrak import read_subject
                    subject = read_subject(png, result[index])
                    if subject: result.subjects[index] = subject
            return result
        finally:
            document.close()
    except ImportError:
        raise ValueError('OCR is unavailable on this server. Continue manually.') from None
    finally:
        _LOCK.release()


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
        result = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '6',
                                 '-c', 'debug_file=/dev/null', 'tsv'], input=table_png,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=max(.1, min(5, timeout)), check=True)
        words = []
        for row in csv.DictReader(io.StringIO(result.stdout.decode('utf-8')), delimiter='\t', quoting=csv.QUOTE_NONE):
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
