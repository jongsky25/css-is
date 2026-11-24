"""Phone journeys through the New advisory flow (with and without JavaScript), fake relay.
Set ADVISORY_SCREENSHOTS=<dir> to save a screenshot of each screen for the PR."""
import os

import pytest

from tests.test_advisory_draft_browser import serve_page
from tests.test_advisory_new import flow  # noqa: F401  (fixture)
from tests.test_document_registration_browser import browser  # noqa: F401  (fixture)

SHOTS = os.environ.get("ADVISORY_SCREENSHOTS", "")


def shot(page, name, scripts):
    if SHOTS and scripts:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)


def fits(page):
    return page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("scripts", [True, False])
def test_phone_journey_activity_general_and_mistake(browser, flow, manager, scripts):  # noqa: F811
    context = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=scripts,
                                  device_scale_factor=2 if SHOTS else 1)
    page = context.new_page()
    serve_page(page, manager)
    try:
        page.goto("http://office.test/advisories")
        assert page.get_by_role("link", name="+ New advisory").first.is_visible() and fits(page)
        shot(page, "1-register-empty", scripts)
        page.get_by_role("link", name="+ New advisory").first.click()
        assert page.get_by_text("What is this advisory for?").is_visible() and fits(page)
        shot(page, "2-choose", scripts)
        page.get_by_role("link", name="An activity already in Office Connect", exact=False).click()
        page.get_by_role("link", name="JOAS Batch 2", exact=False).click()
        assert page.locator("[name=title]").input_value() == "JOAS Batch 2" and fits(page)
        shot(page, "3-details-activity", scripts)
        page.locator("[name=audience][value=both]").check()
        page.get_by_role("button", name="Create advisory").click()
        alert = page.locator("[role=alert]")
        assert alert.is_visible() and "outside email address" in alert.inner_text()
        assert page.locator("[name=title]").input_value() == "JOAS Batch 2" and fits(page)
        shot(page, "4-mistake-kept-values", scripts)
        page.locator("[name=external]").fill("partner@example.org")
        page.get_by_role("button", name="Create advisory").click()
        assert page.get_by_role("link", name="Open in Google Slides").is_visible() and fits(page)
        assert page.locator("[aria-current=step]").inner_text().startswith("Draft")
        shot(page, "5-advisory-home", scripts)
        page.goto("http://office.test/advisories/new/details?kind=general")
        page.locator("[name=title]").fill("Office closed on Friday")
        page.locator(".adv-design").first.click()
        page.get_by_role("button", name="Create advisory").click()
        assert page.get_by_role("heading", name="Office closed on Friday").is_visible() and fits(page)
        page.goto("http://office.test/advisories")
        assert page.get_by_text("Office closed on Friday", exact=False).is_visible() and fits(page)
        shot(page, "6-register", scripts)
    finally:
        context.close()
