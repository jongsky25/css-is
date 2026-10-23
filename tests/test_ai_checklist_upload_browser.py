"""A scanned DPO date remains a reviewable suggestion in the browser."""
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


SCRIPT = (Path(__file__).resolve().parents[1] / "static/js/travel_upload.js").read_text()


def test_suggested_dpo_date_waits_for_staff_to_apply_it():
    options = {"executable_path": os.environ["CSS_TEST_CHROMIUM"]} if os.environ.get("CSS_TEST_CHROMIUM") else {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        page.route("https://office.test/**", lambda route: route.fulfill(status=200, body="<html></html>"))
        page.goto("https://office.test/")
        page.set_content('''<details><summary>Change my answers</summary>
          <input id="dpo_no" value="2026-100"><input id="dpo_date" value=""></details>
          <div class="tv-upload" data-ref="TF-2026-0001" data-code="dpo" data-url="/travel/f/TF-2026-0001/upload">
          <input type="file"><div class="tv-upload-out"></div></div>''')
        page.evaluate("""() => {
          sessionStorage.setItem('tv-upload-msg:TF-2026-0001:dpo', '1 file saved.');
          sessionStorage.setItem('tv-upload-fill:TF-2026-0001',
                                 JSON.stringify({dpo_no:'', dpo_date:'2026-09-20'}));
        }""")
        page.add_script_tag(content=SCRIPT)
        button = page.get_by_role("button", name="Use the suggested DPO date in my answers")
        expect(button).to_be_visible()
        assert page.locator("#dpo_date").input_value() == ""
        button.click()
        assert page.locator("#dpo_date").input_value() == "2026-09-20"
        assert page.locator("#dpo_no").input_value() == "2026-100"
        expect(page.locator("details")).to_have_attribute("open", "")
        browser.close()
