"""Increment 3 of docs/ADVISORY_SLIDES_PLAN.md: send a Slides advisory for review with a snapshot,
access that follows the stage, and the edited-after-approval check. Fake relay, no network or mail."""
import hashlib
import uuid

import pytest

import advisory_new as new_flow
import advisory_review as review
import advisory_slides as slides
import advisory_workflow as aw
import documents as d
import documents_permissions as p
import storage as st
from tests.test_advisory_new import flow, details_form  # noqa: F401  (fixture)

FILE = "SLIDESFILE00000000000001"
DESIGNS = [{"variant": 1, "slide_id": "s1", "placeholders": []}]


def snap(version="5", text=b"v1", comments=()):
    pdf, png = b"%PDF-" + text, b"\x89PNG" + text
    return slides.Outcome(True, value=slides.Snapshot(
        file_id=FILE, version=version, modified_time="t", pdf=pdf, pdf_sha256=hashlib.sha256(pdf).hexdigest(),
        png=png, png_sha256=hashlib.sha256(png).hexdigest(), comments=list(comments)))


class Access:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def __call__(self, file_id, *, editors=(), commenters=(), readers=(), domain=""):
        self.calls.append({"editors": list(editors), "commenters": list(commenters), "readers": list(readers)})
        return slides.Outcome(True, value=[]) if self.ok else slides.Outcome(False, error="unreachable")


@pytest.fixture
def ready(db_path, monkeypatch):
    c = st.connect(db_path); st.init_db(c)
    ids = {}
    for name, role in [("author@doh.gov.ph", "encoder"), ("chief@doh.gov.ph", "viewer"), ("director@doh.gov.ph", "viewer"),
                       ("mate@doh.gov.ph", "viewer")]:
        ids[name.split("@")[0]] = st.get_admin_user_by_id(c, st.create_admin_user(c, name, "hash", "salt", role, active=True))
    bureau = st.add_org_unit(c, "Send bureau", "bureau", "SND")
    division = st.add_org_unit(c, "Send division", "division", "SND/D1")
    section = st.add_org_unit(c, "Send section", "section", "SND/D1/S1")
    for who, unit, title in [("author", section, None), ("mate", section, None), ("chief", division, "Division Chief"),
                             ("director", bureau, "Director")]:
        rp = st.add_rp(c, who.title(), True, unit, email=f"{who}@doh.gov.ph")
        if title:
            c.execute("UPDATE resource_person SET position=?,designation=? WHERE id=?", (title, title, rp))
        c.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (rp, ids[who]["id"]))
    st.set_setting(c, "documents.enabled", "1"); st.set_setting(c, "work.enabled", "1"); c.commit()
    import mailer
    monkeypatch.setattr(mailer, "send", lambda *a, **k: pytest.fail("No email may be sent"))
    u = {k: st.get_admin_user_by_id(c, v["id"]) for k, v in ids.items()}
    form = {"kind": "general", "operation_key": str(uuid.uuid4()), "title": "Office notice", "dates": "", "venue": "",
            "message": "", "attention": "", "contact": "", "link": "", "audience": "internal", "external": "",
            "variant": "1", "unit_id": str(division)}
    aid = new_flow.start(c, u["author"], form, variants=DESIGNS)
    made = slides.Created(id=FILE, url="https://docs.google.com/presentation/d/x/edit", name="n", version="2")
    new_flow.make_file(c, u["author"], aid, create=lambda **k: slides.Outcome(True, value=made))
    yield c, u, aid
    c.close()


def send(c, user, aid, *, taken=None, access=None, reason=""):
    return new_flow.send_for_review(c, user, aid, reason=reason, operation_key=str(uuid.uuid4()),
                                    snapshot=lambda file_id: taken or snap(), access=access or Access())


def act(c, user, aid, action, **extra):
    record = aw.get_visible(c, user, aid)
    return review.mutate(c, user, aid, record["revision"], action,
                         {"operation_key": str(uuid.uuid4()), "reason": "Synthetic " + action, **extra})


def test_send_saves_the_snapshot_and_hands_it_to_the_chief(ready):
    c, u, aid = ready
    access = Access()
    comment = slides.Comment(id="c1", content="Fix the date", author="Mate", created_time="t1", quoted="Dec")
    assert send(c, u["author"], aid, taken=snap(comments=[comment]), access=access) == ""
    record = aw.get_visible(c, u["author"], aid)
    doc = d.raw(c, record["document_id"])
    assert doc["status"] == "in_review" and doc["review_class"] == "chief" and doc["reviewer_id"] == u["chief"]["id"]
    assert aw.artifact(c, u["author"], aid, record["current_revision"], "pdf") == b"%PDF-v1"
    assert record["payload"]["slides"]["version"] == "5"
    assert record["payload"]["slides"]["comments"][0]["content"] == "Fix the date"
    assert access.calls[-1] == {"editors": [], "readers": [],
                                "commenters": ["author@doh.gov.ph", "mate@doh.gov.ph", "chief@doh.gov.ph", "director@doh.gov.ph"]}
    page = new_flow.home(c, u["chief"], aid)
    assert page["headline"].startswith("Waiting for the Division Chief") and page["step"] == 1
    assert page["next_line"] == "Please review the copy below and decide."
    assert page["reviewed"]["comments"][0]["author"] == "Mate"


def test_return_gives_editing_back_and_resend_restarts_chief_review(ready):
    c, u, aid = ready
    send(c, u["author"], aid)
    act(c, u["chief"], aid, "return")
    access = Access()
    assert new_flow.sync_access(c, u["chief"], aid, setter=access) == ""
    assert access.calls[-1]["editors"] == ["author@doh.gov.ph", "mate@doh.gov.ph"]
    first = aw.get_visible(c, u["author"], aid)["current_revision"]
    send(c, u["author"], aid, taken=snap(version="9", text=b"v2"), reason="Fixed the date")
    record = aw.get_visible(c, u["author"], aid)
    assert record["current_revision"] != first and record["ordinal"] == 2
    assert d.raw(c, record["document_id"])["reviewer_id"] == u["chief"]["id"]


def test_approval_then_readers_only_and_edits_after_approval_block_issue(ready):
    c, u, aid = ready
    send(c, u["author"], aid)
    act(c, u["chief"], aid, "endorse")
    act(c, u["director"], aid, "approve")
    access = Access()
    new_flow.sync_access(c, u["author"], aid, setter=access)
    assert access.calls[-1]["editors"] == [] and access.calls[-1]["commenters"] == []
    assert "chief@doh.gov.ph" in access.calls[-1]["readers"]
    same = lambda file_id: slides.Outcome(True, value="5")
    edited = lambda file_id: slides.Outcome(True, value="6")
    down = lambda file_id: slides.Outcome(False, error="unreachable")
    assert new_flow.unchanged_since_approval(c, u["author"], aid, check=same) == ""
    assert "changed after it was approved" in new_flow.unchanged_since_approval(c, u["author"], aid, check=edited)
    assert "Could not check" in new_flow.unchanged_since_approval(c, u["author"], aid, check=down)
    assert new_flow.home(c, u["author"], aid)["headline"] == "Approved by the Director."


def test_failed_snapshot_or_missing_chief_change_nothing(ready):
    c, u, aid = ready
    before = d.raw(c, aw.get_visible(c, u["author"], aid)["document_id"])
    with pytest.raises(ValueError, match="could not be reached"):
        send(c, u["author"], aid, taken=slides.Outcome(False, error="unreachable"))
    with pytest.raises(ValueError, match="too large"):
        send(c, u["author"], aid, taken=slides.Outcome(True, value=slides.Snapshot(
            file_id=FILE, version="5", modified_time="", pdf=b"%PDF-" + b"x" * (aw.MAX_ARTIFACT_BYTES + 1), pdf_sha256="x",
            png=b"\x89PNG", png_sha256="y")))
    c.execute("UPDATE resource_person SET designation=NULL,position=NULL WHERE email='chief@doh.gov.ph'"); c.commit()
    with pytest.raises(ValueError, match="Division Chief"):
        send(c, u["author"], aid)
    after = d.raw(c, before["id"])
    assert (after["status"], after["revision"]) == ("draft", before["revision"])
    assert aw.get_visible(c, u["author"], aid)["current_revision"] is None


def test_only_the_starter_sends_and_a_section_mate_cannot(ready):
    c, u, aid = ready
    with pytest.raises(p.Denied):
        send(c, u["mate"], aid)
    assert d.raw(c, aw.get_visible(c, u["author"], aid)["document_id"])["status"] == "draft"


def test_access_failure_is_reported_but_the_review_stands(ready):
    c, u, aid = ready
    warning = send(c, u["author"], aid, access=Access(ok=False))
    assert "could not be updated" in warning
    assert d.raw(c, aw.get_visible(c, u["author"], aid)["document_id"])["status"] == "in_review"
    assert aw.get_visible(c, u["author"], aid)["kind"] == "general"


def test_send_page_and_old_submit_route(flow, manager):
    """Through the routes: the send form is offered; a missing Chief is explained and nothing changes;
    the generic submit action points to the send button."""
    page = manager.get("/advisories/new/details?kind=general")
    made = manager.post("/advisories/new", data=details_form(page), follow_redirects=False)
    url = made.headers["location"].split("?")[0]
    home = manager.get(url)
    assert "Send to Division Chief" in home.text and "Ready? Send it for review" in home.text
    reply = manager.post(url + "/send", data={"operation_key": str(uuid.uuid4()), "reason": ""})
    assert reply.status_code == 422 and "Division Chief" in reply.text
    assert not [a for a, _ in flow["relay"].calls if a == "advisory_snapshot"]       # checked before touching Google
    old = manager.post(url + "/actions", data={"action": "submit", "expected_revision": "1",
                                               "operation_key": str(uuid.uuid4()), "reason": "x"})
    assert old.status_code == 409 and "Send to Division Chief" in old.text


def issue(c, u, aid, reason="Issue it"):
    import advisory_distribution as dist
    planned = dist.preview(c, u["author"], aid)
    act(c, u["author"], aid, "issue", confirmation=planned["confirmation"], ack_missing="1", reason=reason)
    return planned


def approved(c, u, aid):
    send(c, u["author"], aid)
    act(c, u["chief"], aid, "endorse")
    act(c, u["director"], aid, "approve")


def test_issue_freezes_the_reviewed_copy_and_offers_a_share_message(ready):
    c, u, aid = ready
    approved(c, u, aid)
    assert new_flow.share_info(c, u["author"], aid) is None                  # nothing to share before issue
    planned = issue(c, u, aid)
    assert "author@doh.gov.ph" in planned["recipients"]
    share = new_flow.share_info(c, u["author"], aid, "https://office.example")
    record = aw.get_visible(c, u["author"], aid)
    assert share["caption"] == f"ADVISORY {record['number']}: Office notice"   # general, no link: no URL line
    assert share["image_url"] == f"/advisories/issued/{share['issue_id']}/file.png"
    import advisory_distribution as dist
    assert dist.issued_artifact(c, u["author"], share["issue_id"], "png") == b"\x89PNGv1"
    access = Access()
    new_flow.sync_access(c, u["author"], aid, setter=access)
    assert access.calls[-1]["editors"] == [] and access.calls[-1]["commenters"] == []
    page = new_flow.home(c, u["author"], aid)
    assert page["step"] == 3 and page["headline"] == "Issued."
    assert "group chats" in page["next_line"]
    assert c.execute("SELECT COUNT(*) FROM document_job WHERE kind='dispatch'").fetchone()[0] == len(planned["recipients"])


def test_general_advisories_cannot_be_published_on_a_public_page(ready):
    c, u, aid = ready
    c.execute("UPDATE advisory_record SET details_json=json_set(details_json,'$.audience','both','$.external',json('[\"partner@example.org\"]')) WHERE id=?", (aid,))
    c.commit()
    approved(c, u, aid)
    issued = issue(c, u, aid)
    assert "partner@example.org" in issued["recipients"]
    share = new_flow.share_info(c, u["author"], aid)
    with pytest.raises(ValueError, match="no public activity page"):
        act(c, u["author"], aid, "publish", issue_id=str(share["issue_id"]))


def test_share_caption_uses_the_activity_page_for_activity_advisories(ready):
    c, u, _ = ready
    ev = st.create_event(c, "JOAS Batch 2", "2026-12-15", created_by=u["author"]["username"])
    form = {"kind": "activity", "event_token": ev["event_token"], "operation_key": str(uuid.uuid4()), "title": "JOAS Batch 2",
            "dates": "December 15-17, 2026", "venue": "", "message": "", "attention": "", "contact": "", "link": "",
            "audience": "internal", "external": "", "variant": "1",
            "unit_id": str(c.execute("SELECT id FROM org_unit WHERE path='SND/D1'").fetchone()[0])}
    aid = new_flow.start(c, u["author"], form, variants=DESIGNS)
    made = slides.Created(id="SLIDESFILE00000000000002", url="u", name="n", version="2")
    new_flow.make_file(c, u["author"], aid, create=lambda **k: slides.Outcome(True, value=made))
    taken = snap()
    taken.value.file_id = "SLIDESFILE00000000000002"
    send(c, u["author"], aid, taken=taken)
    act(c, u["chief"], aid, "endorse"); act(c, u["director"], aid, "approve")
    issue(c, u, aid)
    share = new_flow.share_info(c, u["author"], aid, "https://office.example")
    assert share["caption"].endswith(f"(December 15-17, 2026)\nhttps://office.example/e/{ev['event_token']}")


def test_home_page_shows_issue_button_then_share_card(ready, app_mod):
    c, u, aid = ready
    approved(c, u, aid)
    import advisory_distribution as dist
    from starlette.requests import Request

    def render():
        page = new_flow.home(c, u["author"], aid)
        record = aw.get_visible(c, u["author"], aid)
        page["share"] = new_flow.share_info(c, u["author"], aid, "https://office.example")
        req = Request({"type": "http", "method": "GET", "path": f"/advisories/{aid}", "headers": [], "query_string": b"",
                       "state": {"user": u["author"]}})
        return app_mod.templates.get_template("advisory_home.html").render(
            request=req, **page, notice="", error="", reason="", review=None, review_record=record, action_key="k",
            available=True, distribution=dist.screen(c, u["author"], record))
    before = render()
    assert "Issue the advisory" in before and "Share to group chats" not in before
    issue(c, u, aid)
    after = render()
    assert "Share to group chats" in after and "advisory-share.js" in after and "Download image" in after
    assert "Issue the advisory" not in after


def test_issued_page_on_a_phone_fits_and_shows_share(ready, app_mod):
    """Phone width, real CSS: the Share card fits; without the share sheet the Copy button still appears."""
    from tests.test_document_registration_browser import browser as _b  # noqa: F401
    pytest.importorskip("playwright.sync_api")
    import os
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    import advisory_distribution as dist
    from starlette.requests import Request
    c, u, aid = ready
    approved(c, u, aid); issue(c, u, aid)
    page_data = new_flow.home(c, u["author"], aid)
    record = aw.get_visible(c, u["author"], aid)
    page_data["share"] = new_flow.share_info(c, u["author"], aid, "https://office.example")
    req = Request({"type": "http", "method": "GET", "path": f"/advisories/{aid}", "headers": [], "query_string": b"",
                   "state": {"user": u["author"]}})
    html = app_mod.templates.get_template("advisory_home.html").render(
        request=req, **page_data, notice="", error="", reason="", review=None, review_record=record, action_key="k",
        available=True, distribution=dist.screen(c, u["author"], record))
    png = dist.issued_artifact(c, u["author"], page_data["share"]["issue_id"], "png")
    root = Path(__file__).resolve().parent.parent
    shots = os.environ.get("ADVISORY_SCREENSHOTS", "")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as error:  # noqa: BLE001
            pytest.skip(f"Chromium unavailable: {error}")
        context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2 if shots else 1,
                                      ignore_https_errors=True,
                                      permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()

        def serve(route):
            path = route.request.url.split("office.test", 1)[1].split("?")[0]
            if path.startswith("/static/") and (root / path.lstrip("/")).is_file():
                route.fulfill(path=str(root / path.lstrip("/")))
            elif path.endswith("file.png"):
                from PIL import Image
                import io
                buf = io.BytesIO(); Image.new("RGB", (400, 566), (20, 60, 140)).save(buf, "PNG")
                route.fulfill(body=buf.getvalue(), content_type="image/png")
            elif path == "/page":
                route.fulfill(body=html, content_type="text/html")
            else:
                route.fulfill(status=404, body="")
        page.route("**/*", serve)
        # Plain http is not a secure context: no clipboard or share sheet, so those buttons must stay hidden.
        page.goto("http://office.test/page")
        assert page.get_by_role("heading", name="Share to group chats").is_visible()
        assert not page.locator("[data-copy-button]").is_visible() and not page.locator("[data-share-button]").is_visible()
        assert page.get_by_role("link", name="Download image").is_visible()
        page.goto("https://office.test/page")
        assert page.locator("[data-copy-button]").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("[data-copy-button]").click()
        page.wait_for_function("document.querySelector('[data-share-status]').textContent.length > 0")
        assert page.locator("[data-share-status]").inner_text() == "Message copied. Paste it in the chat."
        if shots:
            page.screenshot(path=os.path.join(shots, "7-issued-share.png"), full_page=True)
        browser.close()
    assert png.startswith(b"\x89PNG")
