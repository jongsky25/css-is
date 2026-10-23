"""Conference room R9 over HTTP: the form, the PDF, a guest's form, and the Administrative Section's ordering page."""
from __future__ import annotations
from urllib.parse import quote

import pytest

import auth
import rooms
import rooms_meals as rm
import storage as st
import tzutil as tz
from conftest import in_the_directory

ADMIN_UNIT = "BLHSD/ADMIN"

@pytest.fixture(autouse=True)
def _admin_account_is_in_the_section(app_mod):
    """Only Administrative Section members approve, so the seeded admin account joins it."""
    with in_the_directory(app_mod, "admin@test.local", path="ADMINFX/ADMIN"):
        yield


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c); rooms.ensure_slots(c)
    yield c
    for t in ("room_meal_item", "room_meal", "room_reservation_slot", "room_reservation", "room_block", "room_notice"):
        c.execute(f"DELETE FROM {t}")
    c.commit(); c.close()


def day(conn, extra=3):
    return rooms.add_working_days(conn, tz.today_local(), rooms.LEAD_WORKING_DAYS + extra)


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def uid(conn, name):
    return st.get_admin_user(conn, name)["id"]


def book(conn, who="encoder@test.local", hours=(9, 10, 11, 12), approve=True, title="Quarterly review", meals=True):
    r = rooms.request(conn, title=title, day=day(conn), slot_ids=S(conn, *hours), requester_user_id=uid(conn, who),
                      meals_requested=meals, attendees=20)
    return rooms.approve(conn, r["id"], "admin@test.local") if approve else r


# ---------------------------------------------------------------- the request panel ---

def test_ticking_meals_on_the_request_creates_the_form(viewer, conn):
    d = day(conn)
    r = viewer.post("/rooms/request", data={"day": d.isoformat(), "from_slot": S(conn, 9)[0], "to_slot": S(conn, 12)[0], "title": "With meals",
                                            "modality": "f2f", "attendees": "15", "meals": "1"}, follow_redirects=False)
    assert r.status_code == 303
    rid = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    f = rm.get_form(conn, rid)
    assert f["pax"] == 15 and [i["meal"] for i in f["wanted"]] == ["am_snack", "lunch"]
    assert f"/rooms/meals/{rid}" in viewer.get("/rooms/mine").text


def test_same_day_room_without_meals_succeeds_and_meals_cannot_be_added_later(viewer, conn):
    response = viewer.post("/rooms/request", data={"day": tz.today_local().isoformat(),
                           "from_slot": S(conn, 9)[0], "to_slot": S(conn, 10)[0],
                           "title": "Same-day room", "modality": "f2f"}, follow_redirects=False)
    assert response.status_code == 303
    rid = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    assert "deadline has passed" in viewer.get(f"/rooms/meals/{rid}").text
    for path, data in ((f"/rooms/meals/{rid}/start", {}),
                       (f"/rooms/meals/{rid}", {"pax": "10", "want_lunch": "1", "time_lunch": "12:00"})):
        response = viewer.post(path, data=data)
        assert response.status_code == 400 and "2 calendar days" in response.text
    assert rm.get_form(conn, rid) is None
    assert not rooms.get_reservation(conn, rid)["meals_requested"]


def test_guest_cannot_add_meals_after_deadline(client, conn):
    res = rooms.request_external(conn, name="Guest", org="City", email="guest@example.org", phone="",
                                 title="Same-day visit", day=tz.today_local(), slot_ids=S(conn, 9), consent=True)
    token = auth.make_room_track_token(res["id"])
    base = f"/room/t/{quote(token)}/meals"
    for path, data in ((base + "/start", {}), (base, {"pax": "5", "want_lunch": "1", "time_lunch": "12:00"})):
        response = client.post(path, data=data)
        assert response.status_code == 400 and "2 calendar days" in response.text
    assert rm.get_form(conn, res["id"]) is None


# ------------------------------------------------------------------ the form page ---

def test_the_requester_fills_in_the_form_the_way_it_was_described(encoder, conn):
    r = book(conn)
    page = encoder.get(f"/rooms/meals/{r['id']}").text
    for needle in ("1. Title of the Activity", "Quarterly review", "2. Number of Pax", "3. Special Request for Meals", "4. Meals",
                   "Breakfast", "AM snack", "Lunch", "PM snack", "Requested delivery time", 'name="want_lunch"', 'name="time_pm_snack"'):
        assert needle in page, needle
    resp = encoder.post(f"/rooms/meals/{r['id']}", data={"pax": "40", "special": "3 vegetarian", "want_breakfast": "1", "time_breakfast": "07:45",
                                                         "want_am_snack": "0", "time_am_snack": "10:00", "want_lunch": "1", "time_lunch": "12:30",
                                                         "want_pm_snack": "0", "time_pm_snack": "15:00"}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"].endswith("?saved=1")
    f = rm.get_form(conn, r["id"])
    assert (f["pax"], f["special_request"]) == (40, "3 vegetarian")
    assert {i["meal"]: (i["wanted"], i["deliver_at"]) for i in f["items"]} == {
        "breakfast": (True, "07:45"), "am_snack": (False, "10:00"), "lunch": (True, "12:30"), "pm_snack": (False, "15:00")}
    assert "Meal form saved" in encoder.get(resp.headers["location"]).text


def test_bad_entries_come_back_with_a_message_and_change_nothing(encoder, conn):
    r = book(conn)
    resp = encoder.post(f"/rooms/meals/{r['id']}", data={"pax": "", "want_lunch": "1", "time_lunch": "12:00"})
    assert resp.status_code == 400 and "how many pax" in resp.text
    resp = encoder.post(f"/rooms/meals/{r['id']}", data={"pax": "10", "want_lunch": "1", "time_lunch": "25:61"})
    assert resp.status_code == 400 and "like 10:00" in resp.text
    assert rm.get_form(conn, r["id"])["version"] == 1


def test_only_the_owner_and_the_section_can_open_it(viewer, encoder, admin, conn):
    r = book(conn)
    assert viewer.get(f"/rooms/meals/{r['id']}").status_code == 403
    assert viewer.post(f"/rooms/meals/{r['id']}", data={"pax": "1"}).status_code == 403
    assert viewer.get(f"/rooms/meals/{r['id']}/form.pdf").status_code == 403
    assert encoder.get(f"/rooms/meals/{r['id']}").status_code == 200 and admin.get(f"/rooms/meals/{r['id']}").status_code == 200


def test_asking_for_meals_afterwards(encoder, conn):
    r = book(conn, meals=False)
    assert "No meals have been requested" in encoder.get(f"/rooms/meals/{r['id']}").text
    assert "Request meals" in encoder.get("/rooms/mine").text
    encoder.post(f"/rooms/meals/{r['id']}/start")
    assert rm.get_form(conn, r["id"]) and "4. Meals" in encoder.get(f"/rooms/meals/{r['id']}").text


def test_once_ordering_starts_the_requester_sees_the_form_locked(encoder, conn):
    r = book(conn)
    rm.tag(conn, r["id"], "lunch", "requested", "ana")
    page = encoder.get(f"/rooms/meals/{r['id']}").text
    assert "can no longer be changed here" in page and "disabled" in page and "Save the meal form" not in page
    assert encoder.post(f"/rooms/meals/{r['id']}", data={"pax": "9", "want_lunch": "1", "time_lunch": "12:00"}).status_code == 400


def test_the_pdf(encoder, conn):
    r = book(conn)
    resp = encoder.get(f"/rooms/meals/{r['id']}/form.pdf")
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/pdf" and resp.content.startswith(b"%PDF")
    assert f"meal-request-{r['ref_code'].lower()}.pdf" in resp.headers["content-disposition"]
    assert encoder.get("/rooms/meals/99999/form.pdf").status_code == 403                      # nothing to say about a stranger's id


# ------------------------------------------------------------------------- guests ---

def test_a_guest_fills_in_and_prints_their_own_form(client, conn):
    r = rooms.request_external(conn, name="Ana Cruz", org="NGO", email="ana@ngo.org", phone="", title="Site visit", day=day(conn),
                               slot_ids=S(conn, 9, 10, 11, 12), consent=True, meals_requested=True, attendees=12)
    tok = quote(auth.make_room_track_token(r["id"]))
    assert f"/room/t/{tok}/meals" in client.get(f"/room/t/{tok}").text
    page = client.get(f"/room/t/{tok}/meals")
    assert page.status_code == 200 and "Special Request for Meals" in page.text and "Back to your request" in page.text
    resp = client.post(f"/room/t/{tok}/meals", data={"pax": "14", "special": "halal", "want_lunch": "1", "time_lunch": "11:45"}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"].endswith("/meals?saved=1")
    assert (rm.get_form(conn, r["id"])["pax"], rm.get_form(conn, r["id"])["special_request"]) == (14, "halal")
    assert client.get(f"/room/t/{tok}/meals/form.pdf").content.startswith(b"%PDF")
    assert client.get("/room/t/garbage/meals").status_code == 404


def test_a_guest_link_cannot_open_a_staff_form(client, encoder, conn):
    r = book(conn)
    tok = quote(auth.make_room_track_token(r["id"]))
    assert client.get(f"/room/t/{tok}/meals").status_code == 404 and client.get(f"/room/t/{tok}/meals/form.pdf").status_code == 404


# ------------------------------------------------- the Administrative Section's page ---

def test_the_ordering_page_is_for_the_section(viewer, admin, conn):
    assert viewer.get("/rooms/meals").status_code == 403
    assert viewer.post("/rooms/meals/1/tag", data={"meal": "lunch", "status": "requested"}).status_code == 403
    assert viewer.post("/rooms/meals/1/tag-all", data={}).status_code == 403
    assert admin.get("/rooms/meals").status_code == 200


def test_the_page_shows_what_to_order_with_the_filled_up_information(admin, conn):
    r = book(conn, title="Budget review")
    rm.save_form(conn, r["id"], "encoder@test.local", pax="35", special_request="2 vegetarian", wanted={"am_snack", "lunch"},
                 times={"am_snack": "09:45", "lunch": "12:15"})
    page = admin.get("/rooms/meals").text
    assert "Budget review" in page and "35" in page and "2 vegetarian" in page and "9:45 AM" in page and "12:15 PM" in page
    assert "Not yet requested" in page and "Mark requested" in page and f"/rooms/meals/{r['id']}/form.pdf" in page
    assert "Breakfast" not in page.split("Budget review", 1)[1].split("</section>")[0]               # unwanted meals are not listed


def test_tagging_a_meal_requested_then_delivered_or_not_or_cancelled(admin, conn):
    r = book(conn, hours=(12,))
    back = {"from": "2020-01-01", "to": "2099-01-01", "show": "all"}
    resp = admin.post(f"/rooms/meals/{r['id']}/tag", data={"meal": "lunch", "status": "requested", "note": "Ordered from Caterer X", **back},
                      follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"].endswith(f"#r{r['id']}")
    page = admin.get("/rooms/meals?from=2020-01-01&to=2099-01-01&show=all").text
    assert "Requested" in page and "Ordered from Caterer X" in page and "admin@test.local" in page
    assert "disabled" in page                                                                          # not delivered before the day
    resp = admin.post(f"/rooms/meals/{r['id']}/tag", data={"meal": "lunch", "status": "delivered", **back}, follow_redirects=True)
    assert "hasn&#39;t come yet" in resp.text or "hasn't come yet" in resp.text
    conn.execute("UPDATE room_reservation SET day=?", (tz.today_local().isoformat(),)); conn.commit()
    admin.post(f"/rooms/meals/{r['id']}/tag", data={"meal": "lunch", "status": "delivered", **back})
    assert rm.get_form(conn, r["id"])["items"][2]["status"] == "delivered"
    admin.post(f"/rooms/meals/{r['id']}/tag", data={"meal": "lunch", "status": "requested", **back})        # reopen
    admin.post(f"/rooms/meals/{r['id']}/tag", data={"meal": "lunch", "status": "not_delivered", **back})
    assert rm.get_form(conn, r["id"])["items"][2]["status"] == "not_delivered"


def test_mark_everything_requested_in_one_click(admin, conn):
    r = book(conn, hours=tuple(range(7, 19)))
    resp = admin.post(f"/rooms/meals/{r['id']}/tag-all", data={}, follow_redirects=True)
    assert "Marked as requested" in resp.text
    assert {i["status"] for i in rm.get_form(conn, r["id"])["wanted"]} == {"requested"}
    assert "Nothing is waiting" in admin.post(f"/rooms/meals/{r['id']}/tag-all", data={}, follow_redirects=True).text


def test_the_default_view_hides_finished_and_unapproved_ones(admin, conn):
    done = book(conn, hours=(12,), title="Finished one")
    rm.tag(conn, done["id"], "lunch", "cancelled", "ana")
    wait = book(conn, hours=(10,), title="Waiting on room", approve=False)
    has = lambda url, r: f'id="r{r["id"]}"' in admin.get(url).text                    # a card, not just a mention in the bell
    page = admin.get("/rooms/meals").text
    assert not has("/rooms/meals", done) and not has("/rooms/meals", wait) and "waiting for the room to be approved" in page
    assert has("/rooms/meals?waiting=1&show=all", wait) and has("/rooms/meals?show=all", done)


def test_a_section_member_who_is_not_an_admin_can_use_it_and_sees_the_tab_badge(app_mod, viewer, conn):
    book(conn, hours=(12,))
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        assert viewer.get("/rooms/meals").status_code == 200
        tabs = viewer.get("/rooms").text
        tabs = tabs[tabs.index('class="rm-tabs"'):]   # the room tab strip, past the Office menu
        assert 'href="/rooms/meals"' in tabs and ">1</span>" in tabs.split('href="/rooms/meals"')[1].split("</a>")[0]


def test_the_bell_tells_the_section_a_form_is_ready_until_they_open_the_page(app_mod, viewer, conn):
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        book(conn, hours=(12,))
        assert "meal form is ready to order" in viewer.get("/rooms").text
        viewer.get("/rooms/meals")
        assert "meal form is ready to order" not in viewer.get("/rooms").text


def test_back_links_cannot_be_hijacked(admin, conn):
    r = book(conn, hours=(12,))
    resp = admin.post(f"/rooms/meals/{r['id']}/tag", data={"meal": "lunch", "status": "requested", "from": "https://evil.example", "show": "x"},
                      follow_redirects=False)
    assert resp.headers["location"].startswith("/rooms/meals") and "evil" not in resp.headers["location"].split("#")[0].split("?")[0]
