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
            result = {}
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
                result[index] = completed.stdout.decode('utf-8', errors='replace').strip()
            return result
        finally:
            document.close()
    except ImportError:
        raise ValueError('OCR is unavailable on this server. Continue manually.') from None
    finally:
        _LOCK.release()
