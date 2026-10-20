"""Transient scanned-PDF text and subject readings from a protected OCR worker."""
from ocr_process import MAX_OCR_PAGES, read


class PageReadings(dict):
    """Text mapping with transient field evidence; callers may use it as a dict."""
    def __init__(self, pages=None, subjects=None):
        super().__init__(pages or {})
        self.subjects = subjects or {}


def read_pages(raw, indices, *, cancelled=None):
    pages, subjects = read(raw, indices=indices, cancelled=cancelled)
    return PageReadings(pages, subjects)
