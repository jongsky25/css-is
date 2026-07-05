"""
Seed realistic sample data for the insight dashboard.

Run:  python seed_dashboard_demo.py

It is NON-destructive: it only ADDS responses, and only when the database has
none yet (so it won't double-seed on a re-run). It keeps whatever directory you
already have, looking staff up by name and creating anyone missing. The goal is
enough spread — several people, several events, several months, and real written
comments — that every view of the dashboard has a story to tell.
"""

from __future__ import annotations
import storage as st
import css_is_engine as eng

DB = "css_is.db"

# ARTA value profiles: how a batch of walk-in clients rated each SQD item.
# 5 = Strongly Agree … 1 = Strongly Disagree. We vary SQD4 ("info easy to find")
# to plant a recurring, plain-language weak spot for the "Worth looking at" callout.
B9 = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]

# Per-item offsets from the batch `base`, so the ranked "part by part" / dimension
# bars show a real spread instead of one flat value. Clamped to each scale.
# ARTA (1–5): courtesy strongest, time a touch lower (SQD4/info set separately).
ARTA_OFFSET = {"SQD1": -1, "SQD2": 0, "SQD3": -1, "SQD4": 0, "SQD5": 0,
               "SQD6": 0, "SQD7": +0, "SQD8": 0}
# SERVQUAL B-items (1–7): Responsiveness (B5) strongest, Tangible (B9) weakest,
# so dimensions rank distinctly (Reliability B1–4, Resp B5, Assur B6/7, Emp B8, Tang B9).
B_OFFSET = {"B1": 0, "B2": 0, "B3": -1, "B4": 0, "B5": +1,
            "B6": 0, "B7": 0, "B8": -1, "B9": -2}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def arta_answers(base, info=None):
    """Every SQD around `base` (per ARTA_OFFSET), with SQD4 (information) set to
    `info` when given. Values clamped to 1–5."""
    out = []
    for it in eng.ARTA_HEADLINE_ITEMS:
        if it == "SQD4" and info is not None:
            v = info
        else:
            v = _clamp(base + ARTA_OFFSET.get(it, 0), 1, 5)
        out.append((it, v))
    return out


def f3_answers(perception, expectation=6, osq=4):
    """Each B-item around `perception` (per B_OFFSET), clamped to 1–7, so the
    SERVQUAL dimensions differ from each other."""
    return ([("A", expectation)]
            + [(b, _clamp(perception + B_OFFSET.get(b, 0), 1, 7)) for b in B9]
            + [("C", osq)])


def find_or_make(conn, name, *, is_internal, org_unit_id=None):
    for p in st.list_resource_persons(conn):
        if p["name"].lower() == name.lower() and p["is_internal"] == is_internal:
            return p["id"]
    return st.add_rp(conn, name, is_internal=is_internal, org_unit_id=org_unit_id)


def main():
    conn = st.connect(DB)
    st.init_db(conn)
    st.seed_directory_if_empty(conn)

    if conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]:
        print("Database already has responses — skipping seed (non-destructive).")
        conn.close()
        return

    org = st.org_structure(conn)
    # A section to attribute walk-in service to (first available, else bureau).
    sec = None
    for d in org["divisions"]:
        if d["sections"]:
            sec = d["sections"][0]["id"]; break
    sec = sec or (org["admin_sections"][0]["id"] if org["admin_sections"] else org["bureau"]["id"])
    div_id = org["divisions"][0]["id"] if org["divisions"] else org["bureau"]["id"]

    ana   = find_or_make(conn, "Ana Cruz", is_internal=True, org_unit_id=sec)
    vince = find_or_make(conn, "Dr. Vince Reyes", is_internal=True, org_unit_id=sec)
    jong  = find_or_make(conn, "Jong Ventura", is_internal=True, org_unit_id=div_id)
    maria = find_or_make(conn, "Prof. Maria Santos", is_internal=False)
    guest = find_or_make(conn, "Guest Speaker (External)", is_internal=False)

    # ---------------------------------------------------------------
    # TYPE 1 — ARTA walk-in. One standing form; each response carries its own
    # submission date (the period) and its own "who served you" pick.
    # ---------------------------------------------------------------
    walkin = st.get_or_create_walkin_form(conn)["id"]

    def arta(server, date, base, info, n=6, remark=None, notes=None):
        for i in range(n):
            st.record_response(
                conn, walkin, arta_answers(base, info),
                submitted_at=f"{date}T10:00:00", served_by_rp_id=server,
                remarks=(remark if i == 0 else None),
                item_remarks=(notes if i == 0 else None))

    # Ana — strong overall, but information ("SQD4") consistently weak, every month.
    arta(ana, "2026-02-11", 5, 3, n=8, remark="Very accommodating staff, but your website is hard to navigate — I couldn't find the requirements list.",
         notes={"SQD4": "Took me three calls to learn which documents to bring."})
    arta(ana, "2026-03-12", 5, 3, n=9, remark="Service was quick and the officer was polite. Finding the form online was the hard part.")
    arta(ana, "2026-04-10", 5, 2, n=10, remark="Courteous and fast. Please make the information easier to find on the site.",
         notes={"SQD4": "The website menus are confusing."})
    arta(ana, "2026-05-14", 5, 2, n=9, remark="Quick service, friendly staff. Still struggled to find info beforehand.")

    # Jong — volatile month to month (one rough month, one great month).
    arta(jong, "2026-02-18", 5, 5, n=7, remark="Smooth and easy, thank you!")
    arta(jong, "2026-03-20", 3, 2, n=8, remark="The process took too long and the steps were confusing. Waited over an hour.",
         notes={"SQD1": "Very long wait.", "SQD3": "Too many steps."})
    arta(jong, "2026-04-22", 5, 5, n=8, remark="Fast and clear this time. Big improvement.")
    arta(jong, "2026-05-19", 4, 4, n=8, remark="Reasonable wait, helpful staff.")

    # Vince — also serves walk-ins occasionally, steady and high.
    arta(vince, "2026-03-08", 5, 5, n=10, remark="Knowledgeable and very helpful officer.")
    arta(vince, "2026-05-09", 5, 5, n=11, remark="Excellent service, no issues at all.")

    # ---------------------------------------------------------------
    # TYPE 2 + 3 — Activities (event review + resource persons).
    # ---------------------------------------------------------------
    def event(date, venue, topic, speakers, f2_perception, f2_exp=6):
        """speakers: list of (rp_id, topic, perception, remark, notes). Creates an
        F2 event review plus one F3 per speaker, all sharing date+venue+division."""
        f2 = st.create_form_instance(conn, survey_type=2, form="F2", event_date=date,
                                     venue=venue, topic=topic, lead_org_id=div_id)
        for i in range(10):
            st.record_response(conn, f2, f3_answers(f2_perception, f2_exp),
                               submitted_at=f"{date}T16:00:00",
                               remarks=("Well-organized session." if i == 0 else None))
        for rp_id, sp_topic, perc, remark, notes in speakers:
            f3 = st.create_form_instance(conn, survey_type=3, form="F3", event_date=date,
                                         venue=venue, topic=sp_topic, rp_id=rp_id,
                                         lead_org_id=div_id)
            for i in range(9):
                st.record_response(conn, f3, f3_answers(perc),
                                   submitted_at=f"{date}T16:00:00",
                                   remarks=(remark if i == 0 else None),
                                   item_remarks=(notes if i == 0 else None))

    event("2026-02-15", "Training Hall A", "Immunization Program Orientation",
          [(vince, "VPD Surveillance", 7,
            "Dr. Reyes was extremely knowledgeable and explained the topic clearly.",
            {"B6": "Deep command of the subject."}),
           (maria, "Cold Chain Logistics", 5,
            "Good content but the session started late and ran over time.",
            {"B3": "Did not keep to schedule."})],
          f2_perception=6)

    event("2026-04-18", "Convention Center", "Health Systems Forum",
          [(vince, "Surveillance Systems", 7,
            "Clear, engaging, and well-prepared as always.", None),
           (maria, "Supply Management", 7,
            "Much better this time — very practical and well-paced.", None)],
          f2_perception=6, f2_exp=6)

    event("2026-05-22", "Training Hall B", "Data Quality Workshop",
          [(vince, "Data Validation", 6,
            "Solid as usual, though the room was warm and a bit cramped.",
            {"B9": "Venue was too small for the group."})],
          f2_perception=5)

    # An OUTSIDE event — Vince invited by another agency (F3 only, external organizer).
    other = st.add_external_organizer(conn, "Other Health Agency")
    f3x = st.create_form_instance(conn, survey_type=3, form="F3", event_date="2026-03-28",
                                  venue="Partner Auditorium", topic="Keynote: Equity in Health",
                                  rp_id=vince, organizer_external_id=other)
    for i in range(8):
        st.record_response(conn, f3x, f3_answers(7),
                           submitted_at="2026-03-28T16:00:00",
                           remarks=("Inspiring keynote, fantastic speaker." if i == 0 else None))

    atoms = st.load_atoms(conn)
    print("Seeded.",
          atoms["response_id"].nunique(), "responses /",
          len(atoms), "atoms across",
          sorted(atoms["quarter"].unique().tolist()))
    conn.close()


if __name__ == "__main__":
    main()
