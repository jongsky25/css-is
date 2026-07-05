"""Layer ② — the home "Recently concluded" strip now includes invited / Form-3-only
activities, not just bureau Form-2 events.

Before this, the strip gated on `e.get("f2")`, so a concluded invited event (which is
often Form-3-only, with no Form-2 review) silently never appeared on the home page —
even though it had gathered responses. The fix surfaces it AND (feedback #48) links it
to its resource-person results — the Type-3 report narrowed to that activity — instead
of a generic list (its Form-2 report route would 404), flagged "Invited".
"""
import json
import re
from datetime import timedelta

import storage as st


def _concluded_payload(html):
    """Pull the window.HOME_CONCLUDED = [...] array the home page embeds."""
    m = re.search(r"window\.HOME_CONCLUDED\s*=\s*(\[.*?\]);", html, re.S)
    assert m, "HOME_CONCLUDED array not found on the home page"
    return json.loads(m.group(1))


def test_concluded_invited_f3_activity_appears_and_links_to_rp_report(manager, app_mod):
    conn = st.connect(app_mod.DB)
    # An external organizer makes this an invited/outside grouping.
    ext_id = conn.execute(
        "INSERT INTO external_organizer(name) VALUES ('Partner Org ZZZ')").lastrowid
    recent = (app_mod._today_local() - timedelta(days=6)).isoformat()
    fid = st.create_form_instance(conn, 3, "F3", recent, topic="Invited Concluded ZZZ",
                                  organizer_external_id=ext_id, venue="Partner Hall",
                                  created_by="mgr@x")
    st.record_response(conn, fid, [("SQD1", 6)])      # one real response
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()                        # rebuild atoms on next request

    rows = _concluded_payload(manager.get("/").text)
    hit = next((a for a in rows if a.get("topic") == "Invited Concluded ZZZ"), None)
    assert hit is not None, "a concluded invited F3 activity must appear in the strip"
    # #48: it links to its resource-person results (Type-3 report narrowed to this
    # activity), not the generic invited list. Single form -> id is the row's fid.
    assert hit["url"] == f"/reports?type=3&activity={fid}", \
        "f2-less events open their Type-3 results, not the invited list"
    assert hit["invited"] is True
    assert hit["responses"] == 1


def test_bureau_f2_events_still_link_to_their_report(manager):
    # The other side of the rule: real Form-2 events keep their SERVQUAL report link
    # and are NOT badged invited. Asserted against the delivered DB's real activities
    # (no fabricated F2 — an incomplete one would just exercise the report's own
    # rendering, not this rule).
    rows = _concluded_payload(manager.get("/").text)
    bureau = [a for a in rows if not a["invited"]]
    assert bureau, "the delivered DB should have concluded Form-2 events"
    for a in bureau:
        assert a["url"].startswith("/reports/activities/"), a
        assert a["invited"] is False
