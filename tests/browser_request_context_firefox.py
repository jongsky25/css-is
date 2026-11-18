"""Opt-in Firefox run: install Playwright Firefox, then pass this file to pytest.

The normal CI suite exercises Chromium; this runner reuses the same assertions
without adding an uninstalled-browser skip to the required suite.
"""
import pytest
from playwright.sync_api import sync_playwright
from test_document_request_work_routes import proposal_record
from test_document_understanding_review_routes import review_record
from test_request_context_accessibility import test_remaining_screens_keyboard_round_trip


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        instance = p.firefox.launch()
        yield instance
        instance.close()
