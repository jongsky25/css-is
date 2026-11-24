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
