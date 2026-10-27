"""Opt-in regression for screenshots preserving hidden control attributes."""
import os
import shutil
import pytest

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in browser check')


def test_visual_screenshot_does_not_mutate_hidden_control():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        page=browser.new_page()
        page.set_content('<input type="range" value="35" hidden><svg width="20" height="20"><circle cx="10" cy="10" r="5"/></svg>')
        before=page.locator('input').evaluate('e=>e.outerHTML')
        first=page.screenshot(caret='initial');second=page.screenshot(caret='initial')
        assert first==second
        assert page.locator('input').evaluate('e=>e.outerHTML')==before
        browser.close()
