"""Comment raffle — a face-to-face engagement draw from everyone who left a
comment. Locks the contract:

  * claim_code is stable, clean (no ambiguous glyphs) and non-sequential;
  * raffle_pool enters ONE response per comment — face-to-face AND online — names
    it from the registered attendee when there is one and leaves it anonymous
    otherwise, excludes no-comment responses and demographic-only notes, and works
    for both bureau and outside ("invited") activities;
  * the draw endpoint picks a winner, records it, excludes prior winners (unless
    repeats are allowed), and reports an empty / exhausted pool cleanly;
  * settings + reset round-trip; management routes are gated;
  * a respondent who comments on a raffle activity is shown their claim code.
"""
import re
import storage as st

CODE_RE = re.compile(r"^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{5}$")


# --------------------------------------------------------------------------
# helpers — craft events directly so the unit tests don't depend on the
# heavier /create + registration HTTP flow.
# --------------------------------------------------------------------------

def _rp(conn):
    return conn.execute("SELECT id FROM resource_person LIMIT 1").fetchone()[0]


def _bureau_event(db_path, title, *, modality=None, named=2, anon=1, nocomment=1,
                  itemnote=False, demo_only=False):
    """A bureau activity (Form 2) with a controllable mix of responses. Returns
    (event_token, event_id)."""
    conn = st.connect(db_path)
    f = st.create_form_instance(conn, 2, "F2", "2026-06-12", topic=title, modality=modality)
    ev = st.create_event(conn, title, "2026-06-12", form_instance_ids=[f],
                         created_by="admin@test.local", modality=modality)
    for i in range(named):
        aid, _ = st.register_attendee(conn, ev["id"], name=f"Person {i}",
                                      email=f"p{i}.{title}@x.test", consent_text="ok")
        st.record_response(conn, f, [("A", 6)], remarks=f"Great session {i}", attendee_id=aid)
    for i in range(anon):
        st.record_response(conn, f, [("A", 6)], remarks=f"Loved it {i}")
    for _ in range(nocomment):
        st.record_response(conn, f, [("A", 5)])                       # no words → not eligible
    if itemnote:
        st.record_response(conn, f, [("A", 6)], item_remarks={"A": "make the slides bigger"})
    if demo_only:
        st.record_response(conn, f, [("A", 6)], item_remarks={"SEX": "F", "AFFIL": "DOH"})
    conn.commit(); conn.close()
    return ev["event_token"], ev["id"]


def _outside_event(db_path, title):
    conn = st.connect(db_path)
    rp = _rp(conn)
    f = st.create_form_instance(conn, 3, "F3", "2026-06-12", rp_id=rp, topic="Keynote")
    ev = st.create_event(conn, title, "2026-06-12", form_instance_ids=[f],
                         created_by="admin@test.local", event_kind="outside")
    st.record_response(conn, f, [("RP1", 6)], remarks="anonymous but happy",
                       item_remarks={"SEX": "M", "AFFIL": "DOH"})
    conn.commit(); conn.close()
    return ev["event_token"], ev["id"], f


# --------------------------------------------------------------------------
# claim code
# --------------------------------------------------------------------------

def test_claim_code_is_stable_clean_and_nonsequential():
    a = st.claim_code(101)
    assert a == st.claim_code(101)                 # deterministic
    assert CODE_RE.match(a)                         # 5 chars, unambiguous alphabet
    assert not any(c in a for c in "01IO")          # never the confusable glyphs
    # consecutive ids don't yield visibly related codes
    assert st.claim_code(101) != st.claim_code(102)


# --------------------------------------------------------------------------
# pool eligibility
# --------------------------------------------------------------------------

def test_pool_enters_only_real_face_to_face_comments(db_path):
    _, eid = _bureau_event(db_path, "Pool Basics", named=2, anon=1, nocomment=2,
                           itemnote=True, demo_only=True)
    conn = st.connect(db_path)
    pool = st.raffle_pool(conn, eid)
    conn.close()
    comments = {p["comment"] for p in pool}
    # 2 named + 1 anon + 1 item-note = 4 eligible; no-comment + demographic-only excluded
    assert len(pool) == 4
    assert "make the slides bigger" in comments           # item note counts as a comment
    assert all(CODE_RE.match(p["code"]) for p in pool)
    assert all(p["code"] for p in pool)


def test_pool_names_registered_and_anonymises_walkins(db_path):
    _, eid = _bureau_event(db_path, "Pool Names", named=2, anon=1, nocomment=0)
    conn = st.connect(db_path)
    pool = st.raffle_pool(conn, eid)
    conn.close()
    named = [p for p in pool if p["name"]]
    anon = [p for p in pool if not p["name"]]
    assert len(named) == 2 and {p["name"] for p in named} == {"Person 0", "Person 1"}
    assert len(anon) == 1                                  # the walk-in has no name


def test_pool_enters_online_responses(db_path):
    """Online activities run raffles too (Spot Feedback #41): an online response
    with a comment is now an eligible entry, identified by its claim code."""
    _, eid = _bureau_event(db_path, "Pool Online", modality="online", named=2, anon=1, nocomment=1)
    conn = st.connect(db_path)
    pool = st.raffle_pool(conn, eid)
    conn.close()
    assert len(pool) == 3                                 # 2 named + 1 anon; no-comment excluded
    assert all(CODE_RE.match(p["code"]) for p in pool)


def test_pool_works_for_outside_activity(db_path):
    _, eid, _f = _outside_event(db_path, "Pool Outside")
    conn = st.connect(db_path)
    pool = st.raffle_pool(conn, eid)
    conn.close()
    assert len(pool) == 1
    assert pool[0]["name"] is None                        # outside responses are anonymous
    assert pool[0]["comment"] == "anonymous but happy"
    assert CODE_RE.match(pool[0]["code"])


# --------------------------------------------------------------------------
# settings + draw bookkeeping (storage)
# --------------------------------------------------------------------------

def test_set_event_raffle_roundtrips(db_path):
    token, eid = _bureau_event(db_path, "Raffle Toggle", named=1, anon=0, nocomment=0)
    conn = st.connect(db_path)
    st.set_event_raffle(conn, eid, True, "a DOH tumbler")
    ev = st.get_event(conn, token)
    conn.close()
    assert ev["raffle_enabled"] is True and ev["raffle_prize"] == "a DOH tumbler"


def test_draw_record_exclude_and_reset(db_path):
    _, eid = _bureau_event(db_path, "Draw Bookkeeping", named=2, anon=1, nocomment=0)
    conn = st.connect(db_path)
    pool = st.raffle_pool(conn, eid)
    first = pool[0]["response_id"]
    st.raffle_record_draw(conn, eid, first, "tumbler", "admin@test.local")
    assert st.raffle_drawn_ids(conn, eid) == {first}
    winners = st.raffle_winners(conn, eid)
    assert len(winners) == 1 and winners[0]["response_id"] == first
    assert winners[0]["prize"] == "tumbler"
    n = st.raffle_reset(conn, eid)
    assert n == 1 and st.raffle_drawn_ids(conn, eid) == set()
    conn.close()


# --------------------------------------------------------------------------
# HTTP — settings, draw screen, draw endpoint, reset, auth
# --------------------------------------------------------------------------

def test_settings_route_toggles_raffle(admin, db_path):
    token, eid = _bureau_event(db_path, "HTTP Settings", named=1, anon=0, nocomment=0)
    r = admin.post(f"/activities/{token}/raffle/settings",
                   data={"raffle_enabled": "1", "raffle_prize": "  a mug  "},
                   follow_redirects=False)
    assert r.status_code == 303
    conn = st.connect(db_path)
    ev = st.get_event(conn, token)
    conn.close()
    assert ev["raffle_enabled"] is True and ev["raffle_prize"] == "a mug"   # trimmed


def test_draw_screen_renders_for_manager(admin, db_path):
    token, eid = _bureau_event(db_path, "HTTP Screen", named=2, anon=1, nocomment=0)
    admin.post(f"/activities/{token}/raffle/settings", data={"raffle_enabled": "1"})
    r = admin.get(f"/activities/{token}/raffle")
    assert r.status_code == 200
    assert "DRAW" in r.text and "Animation" in r.text and "Sound" in r.text
    assert "entries left" in r.text
    # all five draw animations are offered, including the duck race
    for anim in ("slot", "wheel", "shuffle", "tumbler", "duckrace"):
        assert f'data-anim="{anim}"' in r.text
    assert 'id="duckLanes"' in r.text


def test_draw_screen_blocked_for_non_manager(viewer, db_path):
    token, _ = _bureau_event(db_path, "HTTP Screen Guard", named=1, anon=0, nocomment=0)
    r = viewer.get(f"/activities/{token}/raffle", follow_redirects=False)
    assert r.status_code == 303                            # bounced to the public page


def test_draw_picks_records_and_excludes_repeats(admin, db_path):
    token, eid = _bureau_event(db_path, "HTTP Draw", named=2, anon=1, nocomment=1)
    admin.post(f"/activities/{token}/raffle/settings", data={"raffle_enabled": "1", "raffle_prize": "prize"})
    seen = set()
    for expect_remaining in (2, 1, 0):                     # pool of 3 commenters
        j = admin.post(f"/activities/{token}/raffle/draw").json()
        assert j["ok"] is True
        w = j["winner"]
        assert CODE_RE.match(w["code"]) and w["code"] not in seen
        assert w["prize"] == "prize"
        assert j["remaining"] == expect_remaining
        seen.add(w["code"])
    # pool exhausted — everyone eligible has already won
    j = admin.post(f"/activities/{token}/raffle/draw").json()
    assert j["ok"] is False and j["error"] == "empty" and j["exhausted"] is True


def test_draw_allow_repeat_can_redraw(admin, db_path):
    token, eid = _bureau_event(db_path, "HTTP Repeat", named=1, anon=0, nocomment=0)
    admin.post(f"/activities/{token}/raffle/settings", data={"raffle_enabled": "1"})
    admin.post(f"/activities/{token}/raffle/draw")                       # only one entry
    j = admin.post(f"/activities/{token}/raffle/draw", data={"allow_repeat": "1"}).json()
    assert j["ok"] is True                                  # repeats allowed → still draws


def test_draw_empty_pool_is_clean(admin, db_path):
    token, _ = _bureau_event(db_path, "HTTP Empty", named=0, anon=0, nocomment=2)
    admin.post(f"/activities/{token}/raffle/settings", data={"raffle_enabled": "1"})
    j = admin.post(f"/activities/{token}/raffle/draw").json()
    assert j["ok"] is False and j["error"] == "empty" and j["exhausted"] is False


def test_reset_route_clears_draws(admin, db_path):
    token, eid = _bureau_event(db_path, "HTTP Reset", named=2, anon=0, nocomment=0)
    admin.post(f"/activities/{token}/raffle/settings", data={"raffle_enabled": "1"})
    admin.post(f"/activities/{token}/raffle/draw")
    r = admin.post(f"/activities/{token}/raffle/reset", follow_redirects=False)
    assert r.status_code == 303
    conn = st.connect(db_path)
    assert st.raffle_drawn_ids(conn, eid) == set()
    conn.close()


def test_draw_forbidden_for_non_manager(viewer, db_path):
    token, _ = _bureau_event(db_path, "HTTP Draw Guard", named=1, anon=0, nocomment=0)
    r = viewer.post(f"/activities/{token}/raffle/draw")
    assert r.status_code == 403


# --------------------------------------------------------------------------
# respondent sees their claim code
# --------------------------------------------------------------------------

def test_thanks_shows_claim_code_when_commenting(client, admin, db_path):
    token, eid, f = _outside_event(db_path, "Thanks Code")
    admin.post(f"/activities/{token}/raffle/settings",
               data={"raffle_enabled": "1", "raffle_prize": "a tumbler"})
    conn = st.connect(db_path)
    qr = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (f,)).fetchone()[0]
    conn.close()
    r = client.post(f"/seq", data={"tokens": qr, f"{qr}::A": "6",
                                   f"remarks::{qr}": "what a great talk"})
    assert r.status_code == 200
    assert "entered in the raffle" in r.text.lower()
    assert "a tumbler" in r.text
    # a visible 5-char claim code is rendered
    assert re.search(r'class="rt-code">[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{5}<', r.text)


def test_thanks_shows_claim_code_for_online_submission(client, admin, db_path):
    """The submit handler now issues a claim code on an ONLINE activity too (Spot
    Feedback #41), not just face-to-face — the thank-you screen enters the rater."""
    conn = st.connect(db_path)
    f = st.create_form_instance(conn, 2, "F2", "2026-06-12", topic="Online Raffle",
                                modality="online")
    ev = st.create_event(conn, "Online Raffle", "2026-06-12", form_instance_ids=[f],
                         created_by="admin@test.local", modality="online")
    token = ev["event_token"]
    qr = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (f,)).fetchone()[0]
    conn.commit(); conn.close()
    admin.post(f"/activities/{token}/raffle/settings",
               data={"raffle_enabled": "1", "raffle_prize": "a tumbler"})
    r = client.post("/seq", data={"tokens": qr, f"{qr}::A": "6",
                                  f"remarks::{qr}": "loved the webinar"})
    assert r.status_code == 200
    assert "entered in the raffle" in r.text.lower()
    assert re.search(r'class="rt-code">[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{5}<', r.text)


def test_thanks_no_code_without_comment(client, admin, db_path):
    token, eid, f = _outside_event(db_path, "Thanks NoCode")
    admin.post(f"/activities/{token}/raffle/settings", data={"raffle_enabled": "1"})
    conn = st.connect(db_path)
    qr = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (f,)).fetchone()[0]
    conn.close()
    # answer but leave no comment → no raffle entry, no code
    r = client.post(f"/seq", data={"tokens": qr, f"{qr}::A": "6"})
    assert r.status_code == 200
    assert "entered in the raffle" not in r.text.lower()
