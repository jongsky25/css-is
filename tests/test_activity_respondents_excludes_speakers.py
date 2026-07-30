"""
Regression: an activity's "N response(s)" count (and the response_ids feeding its
verbatims/demographics/comment-overrides) must reflect its OWN Type-2 event review,
not incidental Type-3 speaker reviews that happen to share the same date+venue+org.

Found while investigating why an activity card showed 212 responses next to a score
computed from a single Type-2 response: `dashboard_insights.build_events` grouped a
lone F2 activity together with 11 unrelated F3 speaker-review forms (5 different
resource persons, same date/section/blank venue — pure grouping-key coincidence) and
summed ALL of their responses into the card's respondent count. The satisfaction
score next to it was already correctly F2-only (activity_servqual / f2_block both
filter survey_type==2 internally) — only the displayed count was inflated. Speakers
have been rated separately on the People page since the 2026-06-12 decoupling, so
their response volume never belonged in an activity's own count.

A group with NO Type-2 review at all (pure "outside engagement", F3-only) still
counts its own F3s — there's nothing else to prefer for that kind of event.
"""
import storage as st
import dashboard_insights as di


def _sec(conn, suffix):
    return st.add_org_unit(conn, f"Test Section {suffix}", "section", f"BLHSD/TestSec-{suffix}")


def test_activity_respondents_excludes_incidental_speaker_reviews(app_mod):
    conn = st.connect(app_mod.DB)
    try:
        sec = _sec(conn, "resp1")
        rp1 = st.add_rp(conn, "Speaker One", is_internal=True, org_unit_id=sec)
        rp2 = st.add_rp(conn, "Speaker Two", is_internal=True, org_unit_id=sec)

        f2 = st.create_form_instance(conn, survey_type=2, form="F2", event_date="2026-05-26",
                                     lead_org_id=sec, topic="The Real Activity")
        f3a = st.create_form_instance(conn, survey_type=3, form="F3", event_date="2026-05-26",
                                      lead_org_id=sec, rp_id=rp1, topic="Speaker One talk")
        f3b = st.create_form_instance(conn, survey_type=3, form="F3", event_date="2026-05-26",
                                      lead_org_id=sec, rp_id=rp2, topic="Speaker Two talk")

        st.record_response(conn, f2, [("A", 6)] + [(b, 6) for b in
                           ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]] + [("C", 6)])
        for _ in range(5):
            st.record_response(conn, f3a, [("A", 6)] + [(b, 6) for b in
                               ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]] + [("C", 6)])
        for _ in range(7):
            st.record_response(conn, f3b, [("A", 6)] + [(b, 6) for b in
                               ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]] + [("C", 6)])
        conn.commit()

        atoms = st.load_atoms(conn)
        events = di.build_events(atoms, st.list_activity_instances(conn))
        ev = next(e for e in events if e["id"] == f2 or f2 in e["instance_ids"])

        assert ev["respondents"] == 1                # not 1 + 5 + 7 = 13
        assert len(ev["response_ids"]) == 1
        # instance_ids stays the full group (section reassignment etc. still
        # need to reach the speaker forms) — only respondents/response_ids narrow.
        assert set(ev["instance_ids"]) == {f2, f3a, f3b}
    finally:
        conn.close()


def test_outside_engagement_with_no_f2_still_counts_its_own_speakers(app_mod):
    """A pure F3 group (external organizer, no Type-2 review at all) has nothing
    else to prefer — it should keep counting its own speaker responses."""
    conn = st.connect(app_mod.DB)
    try:
        sec = _sec(conn, "resp2")
        rp = st.add_rp(conn, "Outside Speaker", is_internal=True, org_unit_id=sec)
        org_ext = st.add_external_organizer(conn, f"Other Agency {rp}")

        f3 = st.create_form_instance(conn, survey_type=3, form="F3", event_date="2026-05-27",
                                     organizer_external_id=org_ext, rp_id=rp, topic="Invited talk")
        for _ in range(4):
            st.record_response(conn, f3, [("A", 6)] + [(b, 6) for b in
                               ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]] + [("C", 6)])
        conn.commit()

        atoms = st.load_atoms(conn)
        events = di.build_events(atoms, st.list_activity_instances(conn))
        ev = next(e for e in events if f3 in e["instance_ids"])

        assert ev["respondents"] == 4
        assert len(ev["response_ids"]) == 4
    finally:
        conn.close()
