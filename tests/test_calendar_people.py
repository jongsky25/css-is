"""Matching the Word calendar's names to accounts (increment B3): the pure matcher,
then the people step of the import."""
from __future__ import annotations
import io
from urllib.parse import urlencode

import docx
import pytest

import calendar_people as cp
import storage as st
from test_calendar_import import month_table

FORM = {"Content-Type": "application/x-www-form-urlencoded"}
REAL_GUIDE = dict(cp.NAME_GUIDE)


@pytest.fixture(autouse=True)
def _no_guide_unless_asked(monkeypatch):
    """The ordinary-matching tests use made-up people, so the real name guide is off
    for them; the guide tests below switch it back on."""
    monkeypatch.setattr(cp, "NAME_GUIDE", {})


# ------------------------------------------------------------------ matcher ---

def person(uid, name, nick=""):
    ws = [w for w in cp._words(name) if w not in cp.HONORIFICS]
    return {"user_id": uid, "name": name, "nickname": " ".join(cp._words(nick)),
            "words": ws, "first": ws[0] if ws else ""}


DIR = [person(1, "Riza Santos"), person(2, "Mae Cruz"), person(3, "Mae Reyes"),
       person(4, "Teodoro Lim", "Tek"), person(5, "Maria Lourdes Malou Garcia", "Malou"),
       person(6, "Jong Bautista"), person(7, "Santos Ramon"), person(8, "Desten Ocampo")]


@pytest.mark.parametrize("raw, key, label", [
    ("Sir Jong", "jong", "Jong"), ("Doc Malou", "malou", "Malou"), ("Ma’am Riz", "riz", "Riz"),
    ("Dr. Mar Wynn", "mar wynn", "Mar Wynn"), ("Dir. Mar", "mar", "Mar"),
    ("Usec Maestral", "maestral", "Maestral"), ("  tek ", "tek", "Tek"),
])
def test_honorifics_are_dropped_from_the_front(raw, key, label):
    assert cp.clean(raw) == (key, label)


@pytest.mark.parametrize("raw", ["Doc", "Sir", "Dr.", "", "  ", "..."])
def test_a_title_alone_is_not_a_name(raw):
    assert cp.clean(raw) is None


def m(key, directory=DIR, aliases=None):
    r = cp.match(key, directory, aliases)
    assert r.pop("guide") is None                    # these tests run with the name guide off
    return r


def test_a_nickname_is_the_best_match():
    assert m("tek") == {"level": 1, "candidates": [4], "status": "suggested"}
    assert m("malou")["level"] == 1 and m("malou")["candidates"] == [5]


def test_a_nickname_beats_a_first_name_someone_else_has():
    d = DIR + [person(9, "Tek Wong")]
    assert m("tek", d) == {"level": 1, "candidates": [4], "status": "suggested"}


def test_a_first_name_matches_when_exactly_one_person_has_it():
    assert m("riza") == {"level": 3, "candidates": [1], "status": "suggested"}
    assert m("jong")["candidates"] == [6]


def test_two_people_with_the_same_first_name_are_ambiguous_and_not_chosen():
    r = m("mae")
    assert r["status"] == "ambiguous" and sorted(r["candidates"]) == [2, 3]


def test_a_first_name_beats_somebody_elses_surname():
    r = m("santos")                       # Ramon Santos's first name is Santos; Riza's is a surname
    assert (r["level"], r["candidates"]) == (3, [7])


def test_a_surname_matches_when_nothing_better_does():
    assert m("garcia") == {"level": 4, "candidates": [5], "status": "suggested"}
    assert m("cruz")["candidates"] == [2]


def test_a_full_name_matches_in_any_order():
    assert m("mae cruz") == {"level": 2, "candidates": [2], "status": "suggested"}
    assert m("cruz mae")["candidates"] == [2]
    assert m("maria garcia")["candidates"] == [5]


def test_a_short_start_is_only_ever_possible_never_pre_selected():
    assert m("riz") == {"level": 5, "candidates": [1], "status": "possible"}
    assert m("mar")["status"] == "possible" and m("mar")["candidates"] == [5]   # "Dir. Mar" is not Maria
    assert m("ma")["status"] == "unmatched"                      # too short to even offer


def test_places_initials_and_strangers_are_unmatched():
    for k in ("palawan", "kjf", "davao city", "ac"):
        assert m(k) == {"level": None, "candidates": [], "status": "unmatched"}


def test_a_remembered_answer_beats_everything_but_only_if_that_person_is_still_here():
    assert m("mae", aliases={"mae": 3}) == {"level": 0, "candidates": [3], "status": "alias"}
    assert m("mae", aliases={"mae": 999})["status"] == "ambiguous"
    assert m("kjf", aliases={"kjf": 4})["status"] == "alias"


def test_expand_splits_two_names_only_when_each_word_is_someone():
    assert cp.expand("Riza Desten", DIR) == ["riza", "desten"]
    assert cp.expand("Riza Palawan", DIR) == ["riza palawan"]            # one word is nobody
    assert cp.expand("Mae Cruz", DIR) == ["mae cruz"]                    # it is a whole name
    assert cp.expand("Sir Jong", DIR) == ["jong"]
    assert cp.expand("Doc", DIR) == []


# ---------------------------------------------------------------- directory ---

@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "ppl.db")); st.init_db(c)
    return c


def acct(conn, label, name=None, nick=None, active=True, archived=False):
    rp = conn.execute("INSERT INTO resource_person(name, is_internal, archived_at) VALUES (?,1,?)",
                      (name, "2026-01-01" if archived else None)).lastrowid if name else None
    uid = st.create_admin_user(conn, f"{label}@test.local", "x", "y", "viewer", rp_id=rp, active=active)
    if nick:
        st.set_user_nickname(conn, uid, nick)
    return uid


def test_the_directory_is_active_accounts_with_names_and_nicknames(conn):
    a = acct(conn, "a", "Riza Santos", nick="Riz")
    acct(conn, "gone", "Old Timer", archived=True)
    acct(conn, "off", "Not Active", active=False)
    b = acct(conn, "b", "Cruz, Mae")                  # "Last, First" is reordered
    c = acct(conn, "c")                               # no directory name: the login stands in
    d = {p["user_id"]: p for p in cp.load_directory(conn)}
    assert set(d) == {a, b, c}
    assert d[a]["nickname"] == "riz" and d[a]["first"] == "riza"
    assert d[b]["name"] == "Mae Cruz" and d[b]["first"] == "mae"
    assert d[c]["name"] == "c@test.local" and d[c]["words"] == []


def test_collect_counts_uses_orders_by_certainty_and_skips_unimported_drafts():
    drafts = [{"title": "Alpha", "people_tokens": ["Riza", "Sir Jong"]},
              {"title": "Beta", "people_tokens": ["Mae", "Palawan", "Riza"]},
              {"title": "Gamma", "people_tokens": ["Tek"]},
              {"title": "Never imported", "people_tokens": ["Desten"]}]
    rows = cp.collect(drafts, {0: 10, 1: 11, 2: 12}, DIR, {}, {"palawan"}, {"tek": 4})
    by = {r["key"]: r for r in rows}
    assert set(by) == {"riza", "jong", "mae", "palawan", "tek"}                 # Desten's draft was skipped
    assert by["riza"]["n"] == 2 and by["riza"]["drafts"] == [0, 1] and by["riza"]["titles"] == ["Alpha", "Beta"]
    assert [r["key"] for r in rows] == ["riza", "jong", "mae", "palawan", "tek"]     # pending first, then dealt with
    assert by["tek"]["decision"] == 4 and by["palawan"]["ignored"]
    assert by["mae"]["match"]["status"] == "ambiguous"


# ------------------------------------------------------------- the page flow ---

from test_calendar_import_page import FORM as _F, batch_id, form_for, post_import, upload  # noqa: E402


def make_docx():
    doc = docx.Document()
    t = month_table(doc, 10, {
        5: [("CALPE Palawan trip (Riza, Mae)", "hl:cyan"), ("CALPE Palawan trip (Riza, Mae)", "hl:cyan")],
        6: [("CALPE Palawan trip (Riza, Mae)", "hl:cyan")],
        7: [("CALPE Budget talk (Tek, Kuya Bong, Palawan)", "hl:yellow")],
        12: [("CALPE Planning (Riza)", "hl:green")]})
    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue()


@pytest.fixture()
def world(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    ids = {"riza": acct(c, "calpe-riza", "Riza Calpe"), "mae1": acct(c, "calpe-mae1", "Mae Calpe-Cruz"),
           "mae2": acct(c, "calpe-mae2", "Mae Calpe-Reyes"),
           "tek": acct(c, "calpe-tek", "Teodoro Calpe", nick="Tek")}
    c.commit()
    yield {"conn": c, **ids}
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALPE %'").fetchall():
        st.cal_delete(c, i)
    c.execute("DELETE FROM calendar_import_batch")
    c.execute("DELETE FROM app_setting WHERE key IN ('calendar_people_aliases','calendar_people_ignored',"
              "'calendar_import_owner_units','calendar_unit_tones')")
    c.execute("DELETE FROM admin_user WHERE username LIKE 'calpe-%'")
    c.execute("DELETE FROM resource_person WHERE name LIKE '%Calpe%'")
    c.commit(); c.close()


def imported(admin, world):
    bid = batch_id(upload(admin, make_docx()))
    assert post_import(admin, bid, form_for(world["conn"], bid)).status_code == 303
    return bid


def people_of(world, title):
    (e,) = [e for e in st.cal_list_between(world["conn"], "2026-10-01", "2026-10-31") if e["title"] == title]
    return e, {p["user_id"]: p for p in e["people"]}


def test_the_people_step_needs_an_admin_and_an_imported_batch(admin, viewer, world):
    bid = batch_id(upload(admin, make_docx()))
    assert admin.get(f"/calendar/import/{bid}/people", follow_redirects=False).status_code == 303   # not imported yet
    post_import(admin, bid, form_for(world["conn"], bid))
    assert viewer.get(f"/calendar/import/{bid}/people").status_code == 403
    assert viewer.post(f"/calendar/import/{bid}/people", content="who_riza=1", headers=FORM).status_code == 403
    assert admin.get(f"/calendar/import/{bid}/people").status_code == 200
    assert "Next: match the names" in admin.get(f"/calendar/import/{bid}").text


def test_page_suggests_only_certain_matches_and_leaves_the_rest(admin, world):
    html = admin.get(f"/calendar/import/{imported(admin, world)}/people").text
    sel = lambda k: html.split(f'name="who_{k}"')[1].split("</select>")[0]               # noqa: E731
    assert f'value="{world["riza"]}" selected' in sel("riza") and "Likely" in html
    assert f'value="{world["tek"]}" selected' in sel("tek")
    for k in ("mae", "kuya bong", "palawan"):
        assert "selected" not in sel(k), k               # ambiguous / unmatched: nothing pre-chosen
    assert "Could be 2 people" in html and "No match" in html
    assert "5 names to check" in html


def test_confirming_adds_people_marks_them_seen_and_remembers(admin, world):
    bid = imported(admin, world)
    last_audit = world["conn"].execute("SELECT COALESCE(MAX(id), 0) FROM audit_log").fetchone()[0]
    form = {"who_riza": world["riza"], "who_mae": world["mae2"], "who_tek": world["tek"],
            "who_palawan": "ignore", "who_kuya bong": ""}
    r = admin.post(f"/calendar/import/{bid}/people", content=urlencode(form), headers=FORM,
                   follow_redirects=False)
    assert r.status_code == 303
    trip, ppl = people_of(world, "CALPE Palawan trip (Riza, Mae)")
    assert set(ppl) == {world["riza"], world["mae2"]} and trip["kind"] in ("meeting", "travel")
    assert all(p["seen_seq"] == trip["sequence"] for p in ppl.values())          # no bell flood
    assert set(people_of(world, "CALPE Budget talk (Tek, Kuya Bong, Palawan)")[1]) == {world["tek"]}
    assert set(people_of(world, "CALPE Planning (Riza)")[1]) == {world["riza"]}
    assert st.cal_get(world["conn"], trip["id"])["sequence"] == trip["sequence"]    # people never bump sequence
    page = admin.get(f"/calendar/import/{bid}/people").text
    assert "Kuya Bong" in page and "1 name to check" in page and "4 names already dealt with" in page
    acts = [r[0] for r in world["conn"].execute(
        "SELECT action FROM audit_log WHERE id > ? AND action = 'calendar_import_people'", (last_audit,))]
    assert len(acts) == 1


def test_a_travel_item_gets_the_travel_role(admin, world):
    doc = docx.Document(); month_table(doc, 10, {6: [("CALPE Technical Assistance on PK (Riza)", "hl:cyan")]})
    buf = io.BytesIO(); doc.save(buf)
    bid = batch_id(upload(admin, buf.getvalue()))
    post_import(admin, bid, form_for(world["conn"], bid))
    admin.post(f"/calendar/import/{bid}/people", content=urlencode({"who_riza": world["riza"]}), headers=FORM)
    _, ppl = people_of(world, "CALPE Technical Assistance on PK (Riza)")
    assert ppl[world["riza"]]["role"] == "travel"


def test_applying_twice_adds_nobody_twice(admin, world):
    bid = imported(admin, world)
    body = urlencode({"who_riza": world["riza"]})
    admin.post(f"/calendar/import/{bid}/people", content=body, headers=FORM)
    admin.post(f"/calendar/import/{bid}/people", content=body, headers=FORM)
    _, ppl = people_of(world, "CALPE Planning (Riza)")
    assert len(ppl) == 1
    revs = st.cal_revisions(world["conn"], people_of(world, "CALPE Planning (Riza)")[0]["id"])
    assert len([r for r in revs if "people" in r["diff"]]) == 1


def test_an_undecided_name_stays_undecided_and_nothing_is_written(admin, world):
    bid = imported(admin, world)
    admin.post(f"/calendar/import/{bid}/people", content=urlencode({"who_riza": "", "who_mae": ""}), headers=FORM)
    assert people_of(world, "CALPE Planning (Riza)")[1] == {}
    assert st.get_setting(world["conn"], "calendar_people_aliases") in (None, "{}")


def test_bad_choices_are_ignored(admin, world):
    bid = imported(admin, world)
    admin.post(f"/calendar/import/{bid}/people", content=urlencode(
        {"who_riza": "999999", "who_mae": "abc", "who_nobody": "1"}), headers=FORM)
    assert people_of(world, "CALPE Planning (Riza)")[1] == {}


def test_answers_are_remembered_for_the_next_upload(admin, world):
    first = imported(admin, world)
    admin.post(f"/calendar/import/{first}/people",
               content=urlencode({"who_mae": world["mae1"], "who_palawan": "ignore"}), headers=FORM)
    doc = docx.Document()
    month_table(doc, 10, {20: [("CALPE Next year thing (Mae, Palawan, Kuya Bong)", "hl:yellow")]})
    buf = io.BytesIO(); doc.save(buf)
    second = batch_id(upload(admin, buf.getvalue()))
    post_import(admin, second, form_for(world["conn"], second))
    html = admin.get(f"/calendar/import/{second}/people").text
    assert "Remembered" in html
    sel = html.split('name="who_mae"')[1].split("</select>")[0]
    assert f'value="{world["mae1"]}" selected' in sel
    assert "1 name already dealt with" in html and "Palawan" in html.split("already dealt with")[1]


def test_two_names_run_together_are_split(admin, world):
    doc = docx.Document(); month_table(doc, 10, {6: [("CALPE Joint thing (Riza Tek)", "hl:cyan")]})
    buf = io.BytesIO(); doc.save(buf)
    bid = batch_id(upload(admin, buf.getvalue()))
    post_import(admin, bid, form_for(world["conn"], bid))
    html = admin.get(f"/calendar/import/{bid}/people").text
    assert 'name="who_riza"' in html and 'name="who_tek"' in html and 'name="who_riza tek"' not in html


def test_a_possible_match_is_offered_but_never_pre_selected(admin, world):
    doc = docx.Document(); month_table(doc, 10, {6: [("CALPE Talk (Riz)", "hl:cyan")]})
    buf = io.BytesIO(); doc.save(buf)
    bid = batch_id(upload(admin, buf.getvalue()))
    post_import(admin, bid, form_for(world["conn"], bid))
    html = admin.get(f"/calendar/import/{bid}/people").text
    sel = html.split('name="who_riz"')[1].split("</select>")[0]
    assert "Maybe" in html and "Riza Calpe" in sel and "selected" not in sel
    assert 'label="Could be"' in sel


# ----------------------------------------------------------- the name guide ---

GUIDE_PEOPLE = [person(1, "Maria Teresa Santiago"), person(2, "Marifel Santiago"),
                person(3, "Ronnel Manaloto"), person(4, "Ronnel John Dela Cruz"),
                person(5, "June Naig"), person(6, "June Perez"), person(7, "Teresita Guzman"),
                person(8, "Irene Hizon", "Mimi"), person(9, "Carole Dela Fuente"),
                person(10, "Kathrine Joyce Flores"), person(11, "Juan Alfonso Perez"),
                person(12, "Mary Anne Milliscent"), person(13, "Maria Lourdes Gajitos"),
                person(14, "Fe Ramos"), person(15, "Apple Charm Agulto")]


@pytest.fixture()
def guide(monkeypatch):
    monkeypatch.setattr(cp, "NAME_GUIDE", dict(REAL_GUIDE))


@pytest.mark.parametrize("key, uid", [
    ("riza", 1), ("riz", 1),            # Maria Teresa Santiago, not Marifel Santiago
    ("feng", 2), ("ronnel", 3), ("rj", 4), ("june", 5), ("tek", 7),
    ("mimi", 8), ("mi", 8), ("carole", 9), ("kjf", 10), ("jap", 11), ("mm", 12),
    ("malou", 13), ("ac", 15),
])
def test_the_name_guide_picks_the_person_it_names(guide, key, uid):
    r = cp.match(key, GUIDE_PEOPLE)
    assert r["status"] == "guided" and r["candidates"] == [uid] and r["guide"]


def test_the_guide_beats_a_first_name_two_people_share(guide):
    assert cp.match("ronnel", GUIDE_PEOPLE)["candidates"] == [3]             # two Ronnels in the directory
    assert cp.match("june", GUIDE_PEOPLE)["candidates"] == [5]               # two Junes


def test_a_name_not_in_the_guide_is_matched_the_ordinary_way(guide):
    assert cp.match("fe", GUIDE_PEOPLE) == {"level": 3, "candidates": [14], "status": "suggested", "guide": None}


def test_the_guide_works_when_the_directory_leaves_out_a_middle_name(guide):
    d = [person(1, "Ronnel Dela Cruz"), person(2, "Ronnel Manaloto")]
    assert cp.match("rj", d)["candidates"] == [1]                           # first + last word


def test_a_guide_person_with_no_active_account_is_unmatched_not_guessed(guide):
    r = cp.match("mar", GUIDE_PEOPLE + [person(20, "Maria Cruz"), person(21, "Mar Santos")])
    assert r["status"] == "unmatched" and r["candidates"] == [] and r["guide"] == "Mar Wynn Bello"
    assert cp.match("mwb", GUIDE_PEOPLE)["guide"] == "Mar Wynn Bello"         # the previous Director, by initials
    assert cp.match("tek", [p for p in GUIDE_PEOPLE if p["user_id"] != 7])["status"] == "unmatched"


def test_two_accounts_for_a_guide_person_are_ambiguous(guide):
    r = cp.match("tek", GUIDE_PEOPLE + [person(30, "Teresita Guzman")])
    assert r["status"] == "ambiguous" and sorted(r["candidates"]) == [7, 30]


def test_a_remembered_answer_still_beats_the_guide(guide):
    assert cp.match("riza", GUIDE_PEOPLE, {"riza": 2})["candidates"] == [2]
    assert cp.match("riza", GUIDE_PEOPLE, {"riza": 2})["status"] == "alias"


def test_not_people_are_flagged(guide):
    assert cp.match("tolosa", GUIDE_PEOPLE)["status"] == "not_person"
    for k in ("mmc", "asf"):
        assert cp.match(k, GUIDE_PEOPLE)["status"] == "unlikely"
    # a place is never swallowed into a two-name split
    assert cp.expand("Riza Tolosa", GUIDE_PEOPLE) == ["riza tolosa"]


def test_honorific_forms_reach_the_guide(guide):
    for raw, uid in (("Ma’am Riz", 1), ("Doc Malou", 13), ("Dr. Malou", 13), ("Dr June", 5),
                     ("Ma’am Mi", 8), ("Doc AC", 15), ("Sir Jong", None)):
        key = cp.clean(raw)[0]
        r = cp.match(key, GUIDE_PEOPLE)
        assert (r["candidates"][0] if r["candidates"] else None) == uid, raw


def test_every_guide_entry_is_well_formed():
    assert all(k == k.lower() and cp.clean(k) and cp.clean(k)[0] == k for k in REAL_GUIDE)
    assert all(len(v.split()) >= 2 for v in REAL_GUIDE.values())


def test_the_page_preselects_guided_names_and_not_a_person(admin, world, monkeypatch):
    monkeypatch.setattr(cp, "NAME_GUIDE", {"riza": "Riza Calpe", "mar": "Mar Wynn Bello"})
    monkeypatch.setattr(cp, "NOT_PEOPLE", {"palawan"})
    html = admin.get(f"/calendar/import/{imported(admin, world)}/people").text
    sel = lambda k: html.split(f'name="who_{k}"')[1].split("</select>")[0]               # noqa: E731
    assert f'value="{world["riza"]}" selected' in sel("riza") and "Name guide · Riza Calpe" in html
    assert 'value="ignore" selected' in sel("palawan")
    assert "Guide says Mar Wynn Bello" not in html          # "mar" is not in this made-up file


def test_the_places_and_teams_in_the_real_file_are_marked_not_people(guide):
    for k in ("cebu", "car", "northern mindanao", "blhsd iqa team", "doh rep", "zbb", "tolosa"):
        assert cp.match(k, GUIDE_PEOPLE)["status"] == "not_person", k
    assert cp.match("car", GUIDE_PEOPLE)["candidates"] == []          # never "Carole"
