"""Conference room R9: the meal request form and its tagging (service rules)."""
from __future__ import annotations
import json
from datetime import date, datetime

import pytest

import rooms
import rooms_meals as rm
import rooms_notify as rn
import room_meal_form
import storage as st
from conftest import join_admin_section

MON = date(2030, 3, 4)
THU = date(2030, 3, 7)
FRI = date(2030, 3, 8)


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "m.db")); st.init_db(c); rooms.ensure_slots(c)
    return c


@pytest.fixture()
def me(conn):
    return st.create_admin_user(conn, "me@test.local", "x", "y", "viewer")


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def book(conn, me, hours=(9, 10, 11), day=THU, meals=True, approve=True, attendees=20, title="Quarterly review"):
    r = rooms.request(conn, title=title, day=day, slot_ids=S(conn, *hours), requester_user_id=me, today=MON,
                      meals_requested=meals, attendees=attendees, actor="me@test.local")
    return rooms.approve(conn, r["id"], "boss@test.local", today=MON) if approve else r


def lines(f):
    return {i["meal"]: (i["wanted"], i["deliver_at"], i["status"]) for i in f["items"]}


# ---------------------------------------------------------------- the starting form ---

@pytest.mark.parametrize("hours, expect", [
    ((9, 10, 11), {"am_snack"}), ((12,), {"lunch"}), ((7, 8), {"breakfast"}), ((14, 15, 16), {"pm_snack"}),
    (tuple(range(7, 19)), {"breakfast", "am_snack", "lunch", "pm_snack"}), ((13,), set())])
def test_meals_start_from_the_hours_booked(conn, me, hours, expect):
    f = rm.get_form(conn, book(conn, me, hours)["id"])
    assert {i["meal"] for i in f["items"] if i["wanted"]} == expect
    assert [i["meal"] for i in f["items"]] == ["breakfast", "am_snack", "lunch", "pm_snack"]


def test_the_form_starts_with_the_title_pax_and_usual_delivery_times(conn, me):
    f = rm.get_form(conn, book(conn, me, tuple(range(7, 19)), attendees=25)["id"])
    assert (f["title"], f["pax"], f["special_request"], f["version"]) == ("Quarterly review", 25, None, 1)
    assert {i["meal"]: i["deliver_at"] for i in f["items"]} == {"breakfast": "07:30", "am_snack": "10:00", "lunch": "12:00", "pm_snack": "15:00"}
    assert all(i["status"] == "pending" for i in f["items"])


def test_an_admin_can_change_when_each_meal_is_suggested_and_arrives(conn, me):
    st.set_setting(conn, "room_meal_times", json.dumps({"lunch": {"hour": 13, "time": "12:45"}}))
    f = rm.get_form(conn, book(conn, me, (13,))["id"])
    assert lines(f)["lunch"][:2] == (True, "12:45")


def test_no_meals_no_form_until_someone_asks(conn, me):
    r = book(conn, me, meals=False)
    assert rm.get_form(conn, r["id"]) is None and rm.ensure_form(conn, r["id"]) is None
    f = rm.ensure_form(conn, r["id"], "me@test.local", force=True)
    assert f and rooms.get_reservation(conn, r["id"])["meals_requested"] == 1
    assert rm.ensure_form(conn, r["id"], force=True)["version"] == 1                    # asking twice changes nothing


# ---------------------------------------------------------------------- editing ---

def test_saving_changes_pax_special_meals_and_times(conn, me):
    r = book(conn, me)
    out = rm.save_form(conn, r["id"], "me@test.local", pax="30", special_request=" 3 vegetarian ", wanted={"am_snack", "lunch"},
                       times={"am_snack": "09:45", "lunch": "12:15", "breakfast": "", "pm_snack": ""})
    assert (out["pax"], out["special_request"], out["version"]) == (30, "3 vegetarian", 2)
    assert lines(out)["am_snack"] == (True, "09:45", "pending") and lines(out)["lunch"][0] is True and lines(out)["pm_snack"][0] is False
    assert "Lunch" in out["changed"] and "pax / special request" in out["changed"] and "PM snack" not in out["changed"]
    assert [a["summary"] for a in st.list_audit(conn, action="room_meal_edit")][0].startswith("Quarterly review: changed")


def test_saving_the_same_thing_is_not_a_new_version(conn, me):
    r = book(conn, me)
    f = rm.get_form(conn, r["id"])
    out = rm.save_form(conn, r["id"], "me@test.local", pax=f["pax"], special_request=None,
                       wanted={i["meal"] for i in f["items"] if i["wanted"]}, times={i["meal"]: i["deliver_at"] for i in f["items"]})
    assert out["version"] == 1 and out["changed"] == []


@pytest.mark.parametrize("kw, msg", [
    (dict(pax="", wanted={"lunch"}), "how many pax"),
    (dict(pax="abc", wanted=set()), "must be a number"),
    (dict(pax="0", wanted=set()), "between 1 and 1000"),
    (dict(pax="5000", wanted=set()), "between 1 and 1000"),
    (dict(pax="5", wanted={"lunch"}, times={"lunch": "noon"}), "like 10:00"),
    (dict(pax="5", wanted={"lunch"}, times={"lunch": "05:00"}), "between 06:00 and 19:00"),
    (dict(pax="5", wanted={"lunch"}, times={"lunch": "21:00"}), "between 06:00 and 19:00"),
    (dict(pax="5", wanted=set(), special_request="x" * 801), "too long"),
])
def test_form_rules(conn, me, kw, msg):
    r = book(conn, me)
    args = {"pax": "5", "special_request": None, "wanted": set(), "times": {}}
    args.update(kw)
    with pytest.raises(rm.MealError, match=msg):
        rm.save_form(conn, r["id"], "me@test.local", **args)
    assert rm.get_form(conn, r["id"])["version"] == 1


def test_a_form_for_a_finished_reservation_cannot_be_edited(conn, me):
    r = book(conn, me); rooms.withdraw(conn, r["id"], me)
    with pytest.raises(rm.MealError, match="no longer active"):
        rm.save_form(conn, r["id"], "me@test.local", pax="5", special_request=None, wanted=set(), times={})


def test_the_requester_is_locked_out_once_ordering_starts_but_the_section_is_not(conn, me):
    r = book(conn, me)
    rm.tag(conn, r["id"], "am_snack", "requested", "ana@test.local")
    with pytest.raises(rm.MealError, match="already started ordering"):
        rm.save_form(conn, r["id"], "me@test.local", pax="9", special_request=None, wanted={"am_snack"}, times={"am_snack": "10:00"})
    out = rm.save_form(conn, r["id"], "ana@test.local", pax="9", special_request=None, wanted={"am_snack"}, times={"am_snack": "10:30"}, is_admin=True)
    line = next(i for i in out["items"] if i["meal"] == "am_snack")
    assert line["status"] == "pending" and "Changed after it was requested" in line["status_note"] and line["deliver_at"] == "10:30"


# ----------------------------------------------------------------------- tagging ---

def test_the_whole_journey(conn, me):
    r = book(conn, me, (12,))
    assert lines(rm.get_form(conn, r["id"]))["lunch"][2] == "pending"
    rm.tag(conn, r["id"], "lunch", "requested", "ana@test.local", "Ordered from Caterer X")
    f = rm.tag(conn, r["id"], "lunch", "delivered", "ana@test.local", today=THU)
    i = next(x for x in f["items"] if x["meal"] == "lunch")
    assert i["status"] == "delivered" and i["status_by"] == "ana@test.local" and i["status_at"]
    acts = [a["summary"] for a in st.list_audit(conn, action="room_meal_tag")]
    assert any("pending -> requested" in a and "Ordered from Caterer X" in a for a in acts) and any("requested -> delivered" in a for a in acts)


@pytest.mark.parametrize("start, to, ok", [
    ("pending", "requested", True), ("pending", "cancelled", True), ("pending", "delivered", False), ("pending", "not_delivered", False),
    ("requested", "delivered", True), ("requested", "not_delivered", True), ("requested", "cancelled", True), ("requested", "pending", True),
    ("delivered", "requested", True), ("delivered", "cancelled", False), ("not_delivered", "requested", True),
    ("cancelled", "pending", True), ("cancelled", "requested", False)])
def test_which_tags_may_follow_which(conn, me, start, to, ok):
    r = book(conn, me, (12,))
    conn.execute("UPDATE room_meal_item SET status=? WHERE reservation_id=? AND meal='lunch'", (start, r["id"])); conn.commit()
    if ok:
        assert next(i for i in rm.tag(conn, r["id"], "lunch", to, "ana", today=THU)["items"] if i["meal"] == "lunch")["status"] == to
    else:
        with pytest.raises(rm.MealError, match="can't go straight"):
            rm.tag(conn, r["id"], "lunch", to, "ana", today=THU)


def test_tagging_guards(conn, me):
    r = book(conn, me, (12,))
    with pytest.raises(rm.MealError, match="isn't part of this request"):
        rm.tag(conn, r["id"], "breakfast", "requested", "ana")
    with pytest.raises(rm.MealError, match="can be tagged"):
        rm.tag(conn, r["id"], "dinner", "requested", "ana")
    with pytest.raises(rm.MealError, match="can be tagged"):
        rm.tag(conn, r["id"], "lunch", "eaten", "ana")
    rm.tag(conn, r["id"], "lunch", "requested", "ana")
    with pytest.raises(rm.MealError, match="hasn't come yet"):
        rm.tag(conn, r["id"], "lunch", "delivered", "ana", today=MON)                      # the day is Thursday
    assert rm.tag(conn, r["id"], "lunch", "delivered", "ana", today=THU)["items"][2]["status"] == "delivered"
    assert rm.tag(conn, r["id"], "lunch", "delivered", "ana", today=THU)                    # same tag again: harmless


def test_nothing_is_ordered_for_a_room_that_is_not_approved(conn, me):
    r = book(conn, me, (12,), approve=False)
    with pytest.raises(rm.MealError, match="only once the room booking is approved"):
        rm.tag(conn, r["id"], "lunch", "requested", "ana")


def test_mark_everything_pending_as_requested(conn, me):
    r = book(conn, me, tuple(range(7, 19)))
    rm.tag(conn, r["id"], "lunch", "requested", "ana"); rm.tag(conn, r["id"], "am_snack", "cancelled", "ana")
    f = rm.tag_all_requested(conn, r["id"], "ana", "Batch order")
    assert {m: v[2] for m, v in lines(f).items()} == {"breakfast": "requested", "am_snack": "cancelled", "lunch": "requested", "pm_snack": "requested"}
    with pytest.raises(rm.MealError, match="Nothing is waiting"):
        rm.tag_all_requested(conn, r["id"], "ana")


# --------------------------------------------------- when the booking goes away ---

def test_withdrawing_cancels_the_meals_and_tells_the_section_if_any_were_ordered(conn, me):
    boss = join_admin_section(conn, st.create_admin_user(conn, "boss@test.local", "x", "y", "admin"))
    r = book(conn, me, (10, 11, 12))
    rm.tag(conn, r["id"], "lunch", "requested", "ana")
    rooms.withdraw(conn, r["id"], me)
    f = rm.get_form(conn, r["id"])
    assert {m: v[2] for m, v in lines(f).items() if v[0]} == {"am_snack": "cancelled", "lunch": "cancelled"}
    note = conn.execute("SELECT text, user_id FROM room_notice WHERE kind='meal_cancel'").fetchall()
    assert note and note[0][1] == boss and "cancel the order with the supplier" in note[0][0]


def test_cancelling_before_anything_was_ordered_needs_no_alarm(conn, me):
    r = book(conn, me)
    rooms.withdraw(conn, r["id"], me)
    assert conn.execute("SELECT COUNT(*) FROM room_notice WHERE kind='meal_cancel'").fetchone()[0] == 0
    assert all(v[2] == "cancelled" for v in lines(rm.get_form(conn, r["id"])).values() if v[0])


def test_delivered_meals_are_never_rewritten(conn, me):
    r = book(conn, me, (12,))
    rm.tag(conn, r["id"], "lunch", "requested", "ana"); rm.tag(conn, r["id"], "lunch", "delivered", "ana", today=THU)
    rm.release(conn, r["id"], "later cancellation")
    assert lines(rm.get_form(conn, r["id"]))["lunch"][2] == "delivered"


def test_a_declined_request_and_a_bumped_booking_and_a_closure_all_release_their_meals(conn, me):
    a = book(conn, me, (9, 10), approve=False); rooms.decline(conn, a["id"], "boss@test.local", "no")
    b = book(conn, me, (9, 10), day=FRI); rooms.encode(conn, by="boss@test.local", title="D", day=FRI, slot_ids=S(conn, 9, 10), ext={"name": "D"},
                                                       bump_reason="x", today=MON)
    c = book(conn, me, (9, 10), day=date(2030, 3, 11)); rooms.add_block(conn, "boss@test.local", date(2030, 3, 11), None, "Repairs", confirm=True, today=MON)
    for r in (a, b, c):
        assert all(v[2] == "cancelled" for v in lines(rm.get_form(conn, r["id"])).values() if v[0]), r["id"]


def test_an_undecided_request_that_expires_releases_its_meals(conn, me):
    r = book(conn, me, approve=False)
    rn.expire_past_requests(conn, date(2030, 3, 8))
    assert all(v[2] == "cancelled" for v in lines(rm.get_form(conn, r["id"])).values() if v[0])


def test_moving_the_booking_carries_the_form_over_and_cancels_the_old_one(conn, me):
    old = book(conn, me, (9, 10, 11))
    rm.save_form(conn, old["id"], "me@test.local", pax="42", special_request="halal", wanted={"am_snack"}, times={"am_snack": "09:30"})
    mv = rooms.request_move(conn, old["id"], date(2030, 3, 14), {"id": me, "username": "me@test.local", "role": "viewer"}, today=MON)
    f = rm.get_form(conn, mv["id"])
    assert (f["pax"], f["special_request"]) == (42, "halal") and lines(f)["am_snack"] == (True, "09:30", "pending")
    rooms.approve(conn, mv["id"], "boss@test.local", today=MON)
    assert all(v[2] == "cancelled" for v in lines(rm.get_form(conn, old["id"])).values() if v[0])
    assert all(v[2] == "pending" for v in lines(rm.get_form(conn, mv["id"])).values() if v[0])


# ------------------------------------------------------------------- notices ---

def test_the_section_is_told_when_a_form_is_ready_and_when_it_changes(conn, me):
    boss = join_admin_section(conn, st.create_admin_user(conn, "boss@test.local", "x", "y", "admin"))
    r = book(conn, me)
    ready = conn.execute("SELECT user_id, bell, text FROM room_notice WHERE kind='meal_form'").fetchall()
    assert ready == [(boss, 1, ready[0][2])] and "A meal form is ready to order" in ready[0][2]
    rm.save_form(conn, r["id"], "me@test.local", pax="31", special_request=None, wanted={"am_snack"}, times={"am_snack": "10:00"})
    assert conn.execute("SELECT version FROM room_notice WHERE kind='meal_revised'").fetchall() == [(2,)]
    assert [b["text"] for b in rn.bell_rows(conn, boss)] == ["2 meal order updates"]
    rn.mark_seen(conn, boss, rn.MEAL_KINDS)
    assert rn.bell_rows(conn, boss) == []


def test_a_form_that_asks_for_no_meal_sends_no_notice(conn, me):
    join_admin_section(conn, st.create_admin_user(conn, "boss@test.local", "x", "y", "admin"))
    book(conn, me, (13,))
    assert conn.execute("SELECT COUNT(*) FROM room_notice WHERE kind='meal_form'").fetchone()[0] == 0


class Mail:
    def __init__(self):
        self.sent = []

    def __call__(self, to, subject, body, html=None, attachments=None):
        self.sent.append((to, subject, body)); return {"sent": True, "detail": "ok"}


def test_the_section_gets_an_email_about_a_meal_form(conn, me):
    join_admin_section(conn, st.create_admin_user(conn, "boss@test.local", "x", "y", "admin"))
    book(conn, me)
    mail = Mail()
    rn.flush(conn, "https://x.test", now=datetime.now(), send=mail)
    got = [m for m in mail.sent if m[0] == "boss@test.local" and "meal form is ready" in m[1]]
    assert got and "https://x.test/rooms/meals" in got[0][2]


# ----------------------------------------------------------------- admin list ---

def test_the_ordering_list_and_its_filters(conn, me):
    a = book(conn, me, (9, 10), day=THU, title="Alpha")
    b = book(conn, me, (12,), day=FRI, title="Bravo")
    c = book(conn, me, (12,), day=date(2030, 3, 11), title="Charlie", approve=False)
    rm.tag_all_requested(conn, b["id"], "ana"); rm.tag(conn, b["id"], "lunch", "delivered", "ana", today=FRI)
    names = lambda **k: [f["title"] for f in rm.list_for_admin(conn, "2030-03-01", "2030-03-31", **k)]
    assert names() == ["Alpha"]                                                         # Bravo is done; Charlie's room isn't approved
    assert names(show="all") == ["Alpha", "Bravo"]
    assert names(show="all", include_unapproved=True) == ["Alpha", "Bravo", "Charlie"]
    assert names(show="all")[0] == "Alpha" and rm.list_for_admin(conn, "2030-04-01", "2030-04-30", show="all") == []
    assert rm.counts(conn, today=MON) == 1                                              # Alpha's am_snack still to request


def test_overall_word(conn, me):
    r = book(conn, me, tuple(range(7, 19)))
    assert rm.overall(rm.get_form(conn, r["id"])) == "pending"
    rm.tag(conn, r["id"], "lunch", "requested", "ana")
    assert rm.overall(rm.get_form(conn, r["id"])) == "mixed"
    for m in ("breakfast", "am_snack", "pm_snack"):
        rm.tag(conn, r["id"], m, "cancelled", "ana")
    assert rm.overall(rm.get_form(conn, r["id"])) == "requested"
    rm.tag(conn, r["id"], "lunch", "cancelled", "ana")
    assert rm.overall(rm.get_form(conn, r["id"])) == "cancelled"


# ------------------------------------------------------------------------- PDF ---

def test_the_pdf_renders_with_the_form_fields(conn, me):
    r = book(conn, me, tuple(range(7, 19)), attendees=25)
    rm.save_form(conn, r["id"], "me@test.local", pax="25", special_request="2 vegetarian", wanted={"lunch", "pm_snack"},
                 times={"lunch": "12:00", "pm_snack": "15:30"})
    form = rm.get_form(conn, r["id"])
    data = room_meal_form.render_pdf(form)
    assert data.startswith(b"%PDF") and len(data) > 2000
    assert room_meal_form.filename(form) == f"meal-request-{r['ref_code'].lower()}.pdf"
    assert [room_meal_form.clock(x) for x in ("07:30", "12:00", "15:30", "00:05", "x", None)] == ["7:30 AM", "12:00 PM", "3:30 PM", "12:05 AM", "x", "—"]


def test_todo_lists_what_is_left_on_a_meal_request():
    form = {"reservation": {"status": "requested"}, "pax": None, "special_request": "",
            "wanted": [{"status": "pending", "deliver_at": "12:00"}]}
    done = [t["done"] for t in rm.todo(form)]
    assert done == [False, False, True, True, False, False, False]
    form.update(pax=20, reservation={"status": "approved"})
    form["wanted"][0]["status"] = "delivered"
    assert [t["done"] for t in rm.todo(form)] == [True, True, True, True, False, True, True]
