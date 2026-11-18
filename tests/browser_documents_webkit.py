"""Explicit WebKit acceptance runner; install Playwright WebKit before running.

Reuses the Chromium journey assertions. This tests WebKit on Linux, not Safari
on an iPhone or a VoiceOver session. Missing browser/dependencies fail the run.
"""
import pytest
from playwright.sync_api import sync_playwright
from test_document_request_work_routes import proposal_record
from test_document_understanding_review_routes import review_record
from test_request_context_accessibility import (
    test_remaining_screens_keyboard_round_trip,
    test_emulated_touch_opens_context_link,
    test_request_navigation_reflows_with_large_text,
)
from test_request_review_pagination import test_phone_keyboard_can_reach_the_last_review_and_return
from test_request_reconciliation_browser import (
    test_keyboard_marks_a_changed_source_as_reviewed,
    test_keyboard_follows_the_target_link_and_applies_the_date_through_the_form,
    test_keyboard_opens_the_history_and_it_fits_the_screen,
)


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        instance = p.webkit.launch()
        yield instance
        instance.close()
